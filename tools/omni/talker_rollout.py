#!/usr/bin/env python3
"""Talker production rollout dataset tool: strict validate / summary / split.

Dataset contract: omni.talker_rollout.v1 (little-endian, fixed-width records).

One directory per captured source turn, published atomically by the C++
writer (tools/omni/omni.cpp). Layout inside sequence_<id>_g<gen>_t<turn>/:

  manifest.json   schema, provenance, sampler config, per-file byte/count/CRC
  conditions.bin  32B header + N x 64B condition records + row_count x 3KB rows
  steps.bin       32B header + M x 84B step records
  hidden.f32      32B header + M x 3KB float32 rows (pre-decision target state)
  feedback.f32    32B header + M x 3KB float32 rows (emb_code row, or zeros
                  for the explicit terminal no-feedback EOS path)
  candidates.bin  32B header + K x 12B candidate records

All multi-byte integers are little-endian. This tool never modifies a
dataset directory; split only writes new manifest files at the output path.
"""

import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SCHEMA = "omni.talker_rollout.v1"
HEADER_BYTES = 32
CONDITION_RECORD_BYTES = 64
STEP_RECORD_BYTES = 84
TENSOR_ROW_BYTES = 768 * 4
CANDIDATE_RECORD_BYTES = 12
HIDDEN_WIDTH = 768
AUDIO_VOCAB = 6562
AUDIO_EOS_CODE = 6561

MAGIC_CONDITIONS = b"OMTLCND1"
MAGIC_STEPS = b"OMTLSTP1"
MAGIC_HIDDEN = b"OMTLHID1"
MAGIC_FEEDBACK = b"OMTLFDB1"
MAGIC_CANDIDATES = b"OMTLCAN1"

DATA_FILES = ("conditions.bin", "steps.bin", "hidden.f32", "feedback.f32", "candidates.bin")

# Step flag bits (mirrors omni.cpp step serialization).
FLAG_FIRST_OVERALL = 1 << 0
FLAG_CONDITION_REFORWARDED = 1 << 1
FLAG_FORCE_NO_EOS = 1 << 2
FLAG_SKIP_PROCESSORS = 1 << 3
FLAG_USE_ARGMAX = 1 << 4
FLAG_IS_EOS = 1 << 5
FLAG_HAS_FEEDBACK = 1 << 6

# Candidate flag bits (mirrors omni.h TalkerRolloutCandidateFlag).
CAND_RAW_TOP1 = 1 << 0
CAND_SELECTED = 1 << 1
CAND_EOS = 1 << 2
CAND_RETAINED = 1 << 3
CAND_MASKED = 1 << 4


class ValidationError(Exception):
    pass


def fail(msg):
    raise ValidationError(msg)


# ─── Binary reading ────────────────────────────────────────────────────────

def read_file_checked(seq_dir, name, manifest):
    path = seq_dir / name
    if not path.is_file():
        fail("missing data file %s" % name)
    data = path.read_bytes()
    entry = manifest["files"].get(name)
    if entry is None:
        fail("manifest has no entry for %s" % name)
    if len(data) != entry["bytes"]:
        fail("%s: size %d != manifest bytes %d" % (name, len(data), entry["bytes"]))
    crc = zlib.crc32(data) & 0xFFFFFFFF
    if crc != entry["crc32"]:
        fail("%s: crc32 %08x != manifest crc32 %08x" % (name, crc, entry["crc32"]))
    return data


def parse_header(data, name, expected_magic, expected_record_bytes):
    if len(data) < HEADER_BYTES:
        fail("%s: truncated header (%d bytes)" % (name, len(data)))
    magic = data[0:8]
    if magic != expected_magic:
        fail("%s: bad magic %r" % (name, magic))
    version, flags, record_bytes, record_count = struct.unpack_from("<HHIQ", data, 8)
    reserved = struct.unpack_from("<Q", data, 24)[0]
    if version != 1:
        fail("%s: unsupported version %d" % (name, version))
    if flags != 0:
        fail("%s: unexpected header flags %d" % (name, flags))
    if record_bytes != expected_record_bytes:
        fail("%s: record size %d != expected %d" % (name, record_bytes, expected_record_bytes))
    if reserved != 0:
        fail("%s: reserved header field nonzero" % name)
    return record_count


def parse_conditions(data, row_count_expected):
    count = parse_header(data, "conditions.bin", MAGIC_CONDITIONS, CONDITION_RECORD_BYTES)
    body = data[HEADER_BYTES:]
    records = []
    for i in range(count):
        off = i * CONDITION_RECORD_BYTES
        (condition_id, chunk_id, src_min, src_max, base_pos, row_offset,
         text_rows, row_count, eos_crc, bos_crc) = struct.unpack_from(
            "<QIiiiQIIII", body, off)
        text_eos_count = body[off + 48]
        audio_bos_count = body[off + 49]
        is_end_of_turn = body[off + 50]
        records.append({
            "condition_id": condition_id,
            "chunk_id": chunk_id,
            "src_cnt_min": src_min,
            "src_cnt_max": src_max,
            "prefill_base_position": base_pos,
            "row_offset": row_offset,
            "text_row_count": text_rows,
            "row_count": row_count,
            "text_eos_row_crc32": eos_crc,
            "audio_bos_row_crc32": bos_crc,
            "text_eos_count": text_eos_count,
            "audio_bos_count": audio_bos_count,
            "is_end_of_turn": bool(is_end_of_turn),
        })
    rows_blob = body[count * CONDITION_RECORD_BYTES:]
    total_rows = len(rows_blob) // TENSOR_ROW_BYTES
    if len(rows_blob) != total_rows * TENSOR_ROW_BYTES:
        fail("conditions.bin: partial trailing condition row")
    if total_rows != row_count_expected:
        fail("conditions.bin: %d rows != manifest condition_row_count %d"
             % (total_rows, row_count_expected))
    rows = [rows_blob[r * TENSOR_ROW_BYTES:(r + 1) * TENSOR_ROW_BYTES]
            for r in range(total_rows)]
    return records, rows


def parse_steps(data):
    count = parse_header(data, "steps.bin", MAGIC_STEPS, STEP_RECORD_BYTES)
    if len(data) != HEADER_BYTES + count * STEP_RECORD_BYTES:
        fail("steps.bin: size does not match %d records (partial trailing record)" % count)
    steps = []
    for i in range(count):
        off = HEADER_BYTES + i * STEP_RECORD_BYTES
        (condition_id, global_step, chunk_id, chunk_step, decision_position,
         n_past_before, n_past_after, previous_code, selected_code,
         selected_token_id, raw_top1_code, candidate_offset, flags,
         candidate_count, rng_digest, _reserved) = struct.unpack_from(
            "<QQIIiiiiiiiQIIQQ", data, off)
        steps.append({
            "condition_id": condition_id,
            "global_step": global_step,
            "chunk_id": chunk_id,
            "chunk_step": chunk_step,
            "decision_position": decision_position,
            "n_past_before_feedback": n_past_before,
            "n_past_after_feedback": n_past_after,
            "previous_code": previous_code,
            "selected_code": selected_code,
            "selected_token_id": selected_token_id,
            "raw_top1_code": raw_top1_code,
            "candidate_offset": candidate_offset,
            "flags": flags,
            "candidate_count": candidate_count,
            "rng_state_digest": rng_digest,
        })
    return steps


def parse_tensor_rows(data, name, magic, expected_count):
    count = parse_header(data, name, magic, TENSOR_ROW_BYTES)
    if len(data) != HEADER_BYTES + count * TENSOR_ROW_BYTES:
        fail("%s: size does not match %d rows (partial trailing row)" % (name, count))
    if count != expected_count:
        fail("%s: %d rows != manifest step_count %d" % (name, count, expected_count))
    return data[HEADER_BYTES:]


def parse_candidates(data):
    count = parse_header(data, "candidates.bin", MAGIC_CANDIDATES, CANDIDATE_RECORD_BYTES)
    if len(data) != HEADER_BYTES + count * CANDIDATE_RECORD_BYTES:
        fail("candidates.bin: size does not match %d records" % count)
    out = []
    for i in range(count):
        off = HEADER_BYTES + i * CANDIDATE_RECORD_BYTES
        code, logit, flags = struct.unpack_from("<ifI", data, off)
        out.append((code, logit, flags))
    return out


def check_finite_rows(blob, name):
    floats = struct.unpack("<%df" % (len(blob) // 4), blob)
    for idx, value in enumerate(floats):
        if not math.isfinite(value):
            fail("%s: non-finite float at flat index %d" % (name, idx))


# ─── Validation ────────────────────────────────────────────────────────────

def load_sequence(seq_dir):
    """Parse + structurally validate one sequence directory. Returns records."""
    if not seq_dir.is_dir():
        fail("not a directory: %s" % seq_dir)
    manifest_path = seq_dir / "manifest.json"
    if not manifest_path.is_file():
        fail("missing manifest.json (incomplete publication)")
    try:
        manifest = json.loads(manifest_path.read_text())
    except ValueError as exc:
        fail("manifest.json is not valid JSON: %s" % exc)

    if manifest.get("schema") != SCHEMA:
        fail("unknown schema %r (expected %r)" % (manifest.get("schema"), SCHEMA))
    if manifest.get("endianness") != "little":
        fail("endianness %r is not 'little'" % manifest.get("endianness"))
    if manifest.get("hidden_width") != HIDDEN_WIDTH:
        fail("hidden_width %r != %d" % (manifest.get("hidden_width"), HIDDEN_WIDTH))
    if manifest.get("audio_vocab") != AUDIO_VOCAB:
        fail("audio_vocab %r != %d" % (manifest.get("audio_vocab"), AUDIO_VOCAB))
    audio_bos = manifest.get("audio_bos_token_id", 151687)

    blobs = {name: read_file_checked(seq_dir, name, manifest) for name in DATA_FILES}

    conditions, cond_rows = parse_conditions(
        blobs["conditions.bin"], manifest.get("condition_row_count", -1))
    steps = parse_steps(blobs["steps.bin"])
    hidden = parse_tensor_rows(blobs["hidden.f32"], "hidden.f32", MAGIC_HIDDEN,
                               manifest.get("step_count", -1))
    feedback = parse_tensor_rows(blobs["feedback.f32"], "feedback.f32", MAGIC_FEEDBACK,
                                 manifest.get("step_count", -1))
    candidates = parse_candidates(blobs["candidates.bin"])

    if len(conditions) != manifest.get("condition_count", -1):
        fail("condition record count != manifest condition_count")
    if len(steps) != manifest.get("step_count", -1):
        fail("step record count != manifest step_count")
    if len(candidates) != manifest.get("candidate_count", -1):
        fail("candidate record count != manifest candidate_count")

    for name in ("conditions.bin", "hidden.f32", "feedback.f32"):
        pass  # finite check below on the row payloads
    for name, blob in (("hidden.f32", hidden), ("feedback.f32", feedback)):
        check_finite_rows(blob, name)
    cond_rows_blob = blobs["conditions.bin"][HEADER_BYTES + len(conditions) * CONDITION_RECORD_BYTES:]
    check_finite_rows(cond_rows_blob, "conditions.bin rows")
    for i, (code, logit, _flags) in enumerate(candidates):
        if not math.isfinite(logit):
            fail("candidates.bin[%d]: non-finite logit" % i)
        if not (0 <= code < AUDIO_VOCAB):
            fail("candidates.bin[%d]: code %d outside 0..%d" % (i, code, AUDIO_VOCAB - 1))

    return {
        "dir": seq_dir,
        "manifest": manifest,
        "audio_bos_token_id": audio_bos,
        "conditions": conditions,
        "condition_rows": cond_rows,
        "steps": steps,
        "hidden": hidden,
        "feedback": feedback,
        "candidates": candidates,
    }


def row_slice(rows, offset, count):
    if offset + count > len(rows):
        fail("condition rows [%d:%d] exceed stored rows" % (offset, offset + count))
    return rows[offset:offset + count]


def validate_sequence(seq_dir, require_complete=False):
    """Full strict validation: structural + production-contract semantics."""
    seq = load_sequence(seq_dir)
    manifest = seq["manifest"]
    steps = seq["steps"]
    conditions = seq["conditions"]
    candidates = seq["candidates"]
    eos_code = manifest.get("audio_eos_code", AUDIO_EOS_CODE)

    if require_complete and manifest.get("complete") is not True:
        fail("sequence is not marked complete (end_reason=%r)"
             % manifest.get("end_reason"))
    if manifest.get("complete") is True and not steps:
        fail("complete sequence has zero steps")

    # ── Conditions: canonical suffix ownership ──────────────────────────
    cond_by_id = {}
    cond_by_chunk = {}
    for cond in conditions:
        cid = cond["condition_id"]
        if cid in cond_by_id:
            fail("duplicate condition_id %d" % cid)
        if cond["audio_bos_count"] != 1:
            fail("condition %d: audio_bos_count %d != 1 (canonical suffix is "
                 "owned by generate_audio_tokens_local)" % (cid, cond["audio_bos_count"]))
        if cond["text_eos_count"] not in (0, 1):
            fail("condition %d: text_eos_count %d not in {0,1}" % (cid, cond["text_eos_count"]))
        if cond["row_count"] != cond["text_row_count"] + cond["text_eos_count"] + 1:
            fail("condition %d: row_count %d != text %d + eos %d + 1 audio BOS"
                 % (cid, cond["row_count"], cond["text_row_count"], cond["text_eos_count"]))
        rows = row_slice(seq["condition_rows"], cond["row_offset"], cond["row_count"])
        bos_row = rows[-1]
        bos_crc = zlib.crc32(bos_row) & 0xFFFFFFFF
        if bos_crc != cond["audio_bos_row_crc32"]:
            fail("condition %d: audio BOS row crc %08x != recorded %08x"
                 % (cid, bos_crc, cond["audio_bos_row_crc32"]))
        if cond["text_eos_count"] == 1:
            eos_crc = zlib.crc32(rows[-2]) & 0xFFFFFFFF
            if eos_crc != cond["text_eos_row_crc32"]:
                fail("condition %d: text EOS row crc %08x != recorded %08x"
                     % (cid, eos_crc, cond["text_eos_row_crc32"]))
        if cond["is_end_of_turn"] and cond["text_eos_count"] != 1:
            fail("condition %d: end-of-turn condition must carry a text EOS row" % cid)
        if cond["chunk_id"] in cond_by_chunk:
            fail("chunk %d has more than one condition" % cond["chunk_id"])
        cond_by_id[cid] = cond
        cond_by_chunk[cond["chunk_id"]] = cond

    if conditions:
        chunk_ids = [c["chunk_id"] for c in conditions]
        if chunk_ids != sorted(chunk_ids) or len(set(chunk_ids)) != len(chunk_ids):
            fail("condition chunk ids %r are not strictly increasing" % chunk_ids)
        expected = list(range(chunk_ids[0], chunk_ids[0] + len(chunk_ids)))
        if chunk_ids != expected:
            fail("condition chunk ids %r are not contiguous" % chunk_ids)
        # chunk_idx is session-monotonic in the duplex server; only a turn
        # that starts a session begins at chunk 0 (and therefore position 0).
        if chunk_ids[0] == 0 and cond_by_chunk[0]["prefill_base_position"] != 0:
            fail("session-first condition must prefill from position 0")

    # ── Steps: labels, positions, n_past, EOS/feedback ──────────────────
    if not steps:
        return seq  # empty incomplete sequence is structurally valid

    first_overall_seen = False
    prev_by_chunk = {}
    prev_global = None
    cand_cursor = 0
    for idx, step in enumerate(steps):
        cond = cond_by_id.get(step["condition_id"])
        if cond is None:
            fail("step %d references unknown condition_id %d"
                 % (idx, step["condition_id"]))
        if cond["chunk_id"] != step["chunk_id"]:
            fail("step %d chunk %d != its condition chunk %d"
                 % (idx, step["chunk_id"], cond["chunk_id"]))

        if prev_global is not None and step["global_step"] != prev_global + 1:
            fail("step %d: global_step %d not contiguous after %d"
                 % (idx, step["global_step"], prev_global))
        prev_global = step["global_step"]

        for field in ("selected_code", "raw_top1_code"):
            if not (0 <= step[field] < AUDIO_VOCAB):
                fail("step %d: %s %d outside 0..%d"
                     % (idx, field, step[field], AUDIO_VOCAB - 1))
        if step["previous_code"] != -1 and not (0 <= step["previous_code"] < AUDIO_VOCAB):
            fail("step %d: previous_code %d outside 0..%d or -1"
                 % (idx, step["previous_code"], AUDIO_VOCAB - 1))
        if step["selected_token_id"] != seq["audio_bos_token_id"] + step["selected_code"]:
            fail("step %d: selected_token_id %d != audio_bos %d + code %d"
                 % (idx, step["selected_token_id"], seq["audio_bos_token_id"],
                    step["selected_code"]))

        flags = step["flags"]
        is_eos = bool(flags & FLAG_IS_EOS)
        has_feedback = bool(flags & FLAG_HAS_FEEDBACK)

        if step["decision_position"] != step["n_past_before_feedback"]:
            fail("step %d: decision_position %d != n_past_before_feedback %d"
                 % (idx, step["decision_position"], step["n_past_before_feedback"]))

        if has_feedback:
            if step["n_past_after_feedback"] != step["n_past_before_feedback"] + 1:
                fail("step %d: feedback must advance n_past by 1 (%d -> %d)"
                     % (idx, step["n_past_before_feedback"], step["n_past_after_feedback"]))
            fb = seq["feedback"][idx * TENSOR_ROW_BYTES:(idx + 1) * TENSOR_ROW_BYTES]
            if fb.count(0) == len(fb):
                fail("step %d: has_feedback but feedback row is all zeros" % idx)
        else:
            if is_eos is not True:
                fail("step %d: no feedback is only valid for the terminal EOS path" % idx)
            if step["selected_code"] != eos_code:
                fail("step %d: no-feedback EOS carries selected_code %d != EOS %d"
                     % (idx, step["selected_code"], eos_code))
            if step["n_past_after_feedback"] != step["n_past_before_feedback"]:
                fail("step %d: no-feedback EOS must leave n_past unchanged" % idx)
            fb = seq["feedback"][idx * TENSOR_ROW_BYTES:(idx + 1) * TENSOR_ROW_BYTES]
            if fb.count(0) != len(fb):
                fail("step %d: no-feedback EOS must serialize a zero feedback row" % idx)

        hd = seq["hidden"][idx * TENSOR_ROW_BYTES:(idx + 1) * TENSOR_ROW_BYTES]
        if hd.count(0) == len(hd):
            fail("step %d: hidden row is all zeros" % idx)

        if flags & FLAG_FIRST_OVERALL:
            # A duplex turn may contain several SPEAK response segments
            # separated by LISTEN pauses; each segment restarts from its own
            # saved condition, so the marker may legitimately repeat.
            first_overall_seen = True
            if not (flags & FLAG_CONDITION_REFORWARDED):
                fail("step %d: first_overall decision must follow the saved-condition re-forward" % idx)
            if step["chunk_step"] != 0 or step["previous_code"] != -1:
                fail("step %d: first_overall decision must be chunk_step 0 with no previous code" % idx)
            if cond["prefill_base_position"] != 0:
                fail("step %d: re-forwarded segment must restart from position 0 "
                     "(base %d)" % (idx, cond["prefill_base_position"]))
        if step["chunk_step"] == 0 and idx > 0 and not (flags & FLAG_FIRST_OVERALL):
            # The duplex sampler reads its repetition window from the
            # chunk-local token list, which is empty at a chunk boundary, so
            # previous_code == -1 there is the faithful production value
            # (chunk-initial decisions skip processors anyway).
            pass

        # Position contract inside a chunk: first decision sits right after the
        # canonical condition prefill; later decisions continue from the
        # previous step's post-feedback position.
        if step["chunk_step"] == 0:
            expected = cond["prefill_base_position"] + cond["row_count"]
            if step["decision_position"] != expected:
                fail("step %d: first chunk decision position %d != prefill base %d + rows %d"
                     % (idx, step["decision_position"], cond["prefill_base_position"],
                        cond["row_count"]))
        else:
            prev = prev_by_chunk.get(step["chunk_id"])
            if prev is None:
                fail("step %d: chunk_step %d appears before chunk_step 0"
                     % (idx, step["chunk_step"]))
            if step["chunk_step"] != prev["chunk_step"] + 1:
                fail("step %d: chunk_step %d not contiguous after %d"
                     % (idx, step["chunk_step"], prev["chunk_step"]))
            if step["decision_position"] != prev["n_past_after_feedback"]:
                fail("step %d: decision position %d != previous post-feedback %d "
                     "(position discontinuity)"
                     % (idx, step["decision_position"], prev["n_past_after_feedback"]))
        prev_by_chunk[step["chunk_id"]] = step

        # Candidate block accounting and flag coherence.
        if step["candidate_offset"] != cand_cursor:
            fail("step %d: candidate_offset %d != running cursor %d"
                 % (idx, step["candidate_offset"], cand_cursor))
        block = candidates[cand_cursor:cand_cursor + step["candidate_count"]]
        if len(block) != step["candidate_count"]:
            fail("step %d: candidate block exceeds candidates.bin" % idx)
        cand_cursor += step["candidate_count"]
        codes = [c[0] for c in block]
        if step["selected_code"] not in codes:
            fail("step %d: selected code %d missing from its candidate block"
                 % (idx, step["selected_code"]))
        if step["raw_top1_code"] not in codes:
            fail("step %d: raw top-1 code %d missing from its candidate block"
                 % (idx, step["raw_top1_code"]))
        for code, _logit, cflags in block:
            if code == eos_code and not (cflags & CAND_EOS):
                fail("step %d: EOS code candidate missing the eos flag" % idx)
        selected_flags = [c[2] for c in block if c[0] == step["selected_code"]]
        if not any(f & CAND_SELECTED for f in selected_flags):
            fail("step %d: selected candidate missing the selected flag" % idx)
        if not any(f & CAND_RAW_TOP1 for f in (c[2] for c in block if c[0] == step["raw_top1_code"])):
            fail("step %d: raw top-1 candidate missing the raw_top1 flag" % idx)

    if cand_cursor != len(candidates):
        fail("candidate accounting: steps cover %d of %d candidates"
             % (cand_cursor, len(candidates)))

    chunk_seq = [s["chunk_id"] for s in steps]
    if chunk_seq != sorted(chunk_seq):
        fail("steps are not ordered by chunk id")

    if not first_overall_seen:
        fail("no first_overall marker in a non-empty sequence")

    # Every captured chunk must actually produce decisions.
    for cond in conditions:
        if cond["chunk_id"] not in prev_by_chunk:
            fail("condition chunk %d registered but produced no steps" % cond["chunk_id"])

    # Complete turn: last step must be terminal (final-chunk EOS with feedback,
    # or the explicit no-feedback EOS), and its condition is_end_of_turn.
    if manifest.get("complete") is True:
        last = steps[-1]
        if not (last["flags"] & FLAG_IS_EOS):
            fail("complete sequence does not end on an EOS decision")
        last_cond = cond_by_id[last["condition_id"]]
        if not last_cond["is_end_of_turn"]:
            fail("complete sequence's final condition is not end-of-turn")

    return seq


# ── Summary / split ────────────────────────────────────────────────────────

def iter_sequence_dirs(root):
    return sorted(p for p in root.iterdir()
                  if p.is_dir() and (p / "manifest.json").is_file())


def sequence_digest(seq):
    """Content digest over labels + tensor bytes, used for leakage grouping."""
    h = hashlib.sha256()
    h.update(b"omni.talker_rollout.v1/digest/1")
    for step in seq["steps"]:
        h.update(struct.pack("<Qi", step["global_step"], step["selected_code"]))
    h.update(b"".join(seq["condition_rows"]))
    return h.hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(root):
    root = Path(root)
    seq_dirs = iter_sequence_dirs(root)
    summary = {"root": str(root), "sequences": len(seq_dirs),
               "complete": 0, "incomplete": 0, "steps": 0, "conditions": 0,
               "eos_steps": 0, "no_feedback_eos": 0, "media_types": {},
               "failures": []}
    for seq_dir in seq_dirs:
        try:
            seq = validate_sequence(seq_dir)
        except ValidationError as exc:
            summary["failures"].append({"sequence": seq_dir.name, "error": str(exc)})
            continue
        m = seq["manifest"]
        summary["steps"] += len(seq["steps"])
        summary["conditions"] += len(seq["conditions"])
        if m.get("complete"):
            summary["complete"] += 1
        else:
            summary["incomplete"] += 1
        for step in seq["steps"]:
            flags = step["flags"]
            if flags & FLAG_IS_EOS:
                summary["eos_steps"] += 1
                if not (flags & FLAG_HAS_FEEDBACK):
                    summary["no_feedback_eos"] += 1
        media = str(m.get("media_type"))
        summary["media_types"][media] = summary["media_types"].get(media, 0) + 1
    return summary


def split_dataset(root, out_path, ratio, seed, digest_group):
    import random
    root = Path(root)
    seq_dirs = iter_sequence_dirs(root)
    if not seq_dirs:
        fail("no sequences under %s" % root)

    loaded = []
    groups = {}
    for seq_dir in seq_dirs:
        seq = validate_sequence(seq_dir, require_complete=False)
        digest = sequence_digest(seq)
        loaded.append((seq_dir, seq["manifest"], digest))
        key = ("digest", digest) if digest_group else ("seq", seq_dir.name)
        groups.setdefault(key, []).append(seq_dir)

    keys = sorted(groups, key=lambda k: min(p.name for p in groups[k]))
    rng = random.Random(seed)
    rng.shuffle(keys)

    held_count = max(1, int(round(len(keys) * (1.0 - ratio)))) if len(keys) > 1 else 0
    held_keys = set(keys[:held_count])

    train, held = [], []
    for key in keys:
        target = held if key in held_keys else train
        for seq_dir in groups[key]:
            manifest = next(m for p, m, _d in loaded if p == seq_dir)
            digest = next(d for p, _m, d in loaded if p == seq_dir)
            entry = {
                "sequence": seq_dir.name,
                "request_generation": manifest.get("request_generation"),
                "turn_id": manifest.get("turn_id"),
                "complete": manifest.get("complete"),
                "step_count": manifest.get("step_count"),
                "content_digest": digest,
                "files": {name: file_sha256(seq_dir / name)
                          for name in ("manifest.json",) + DATA_FILES},
            }
            target.append(entry)

    # No sequence may appear in both splits, and digest groups never split.
    train_names = {e["sequence"] for e in train}
    held_names = {e["sequence"] for e in held}
    overlap = train_names & held_names
    if overlap:
        fail("split leakage: %r present in both splits" % sorted(overlap))
    if digest_group:
        digests = {}
        for entry in train:
            digests.setdefault(entry["content_digest"], "train")
        for entry in held:
            prior = digests.get(entry["content_digest"])
            if prior is not None:
                fail("digest group crossed splits: %s" % entry["content_digest"])

    split_manifest = {
        "schema": SCHEMA + "/split/1",
        "root": str(root),
        "seed": seed,
        "ratio": ratio,
        "digest_grouping": bool(digest_group),
        "group_count": len(keys),
        "train": train,
        "held_out": held,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(split_manifest, indent=2) + "\n")
    return split_manifest


# ─── Synthetic self-test ───────────────────────────────────────────────────

def _append_u16(buf, v):
    buf.extend(struct.pack("<H", v))


def _append_u32(buf, v):
    buf.extend(struct.pack("<I", v & 0xFFFFFFFF))


def _append_u64(buf, v):
    buf.extend(struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))


def _append_i32(buf, v):
    buf.extend(struct.pack("<i", v))


def _append_f32(buf, v):
    buf.extend(struct.pack("<f", v))


def _header(magic, record_bytes, count):
    buf = bytearray(magic)
    _append_u16(buf, 1)
    _append_u16(buf, 0)
    _append_u32(buf, record_bytes)
    _append_u64(buf, count)
    _append_u64(buf, 0)
    assert len(buf) == HEADER_BYTES
    return bytes(buf)


def _float_row(seed_value):
    row = bytearray()
    for i in range(HIDDEN_WIDTH):
        _append_f32(row, seed_value + i * 1e-3)
    return bytes(row)


def write_sequence(path, *, steps_spec, complete=True, end_reason="turn_complete",
                   request_generation=7, turn_id=3, media_type=2, duplex=True,
                   corrupt=None):
    """Build a synthetic sequence dir. steps_spec: list of dicts describing
    chunks: [{"chunk_id":0, "text_rows":2, "is_end_of_turn":False,
              "decisions":[{"code":10}, ...]} ...]"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    conditions = []
    rows = bytearray()
    steps = []
    hidden = bytearray()
    feedback = bytearray()
    candidates = bytearray()
    cand_count = 0
    base = 0
    global_step = 0
    prev_code = -1
    first_overall = True
    n_past = 0

    for chunk in steps_spec:
        row_offset = len(rows) // TENSOR_ROW_BYTES
        text_rows = chunk["text_rows"]
        eos_row = chunk.get("is_end_of_turn", False)
        row_count = text_rows + (1 if eos_row else 0) + 1
        for r in range(text_rows):
            rows.extend(_float_row(0.10 + chunk["chunk_id"] + r * 0.01))
        if eos_row:
            rows.extend(_float_row(0.50 + chunk["chunk_id"]))
        bos_row = _float_row(0.90 + chunk["chunk_id"])
        rows.extend(bos_row)
        cond = {
            "condition_id": chunk["chunk_id"],
            "chunk_id": chunk["chunk_id"],
            "src_cnt_min": chunk["chunk_id"],
            "src_cnt_max": chunk["chunk_id"],
            "prefill_base_position": base,
            "row_offset": row_offset,
            "text_row_count": text_rows,
            "row_count": row_count,
            "text_eos_row_crc32": (zlib.crc32(rows[(row_offset + text_rows) * TENSOR_ROW_BYTES:
                                                   (row_offset + text_rows + 1) * TENSOR_ROW_BYTES]) & 0xFFFFFFFF)
                                  if eos_row else 0,
            "audio_bos_row_crc32": zlib.crc32(bos_row) & 0xFFFFFFFF,
            "text_eos_count": 1 if eos_row else 0,
            "audio_bos_count": 1,
            "is_end_of_turn": eos_row,
        }
        conditions.append(cond)

        n_past = base + row_count  # after condition prefill
        for chunk_step, dec in enumerate(chunk["decisions"]):
            code = dec["code"]
            is_eos = dec.get("is_eos", False)
            no_fb = dec.get("no_feedback", False)
            flags = 0
            if first_overall:
                flags |= FLAG_FIRST_OVERALL | FLAG_CONDITION_REFORWARDED
            if dec.get("force_no_eos"):
                flags |= FLAG_FORCE_NO_EOS
            if chunk_step == 0 and not first_overall:
                flags |= FLAG_SKIP_PROCESSORS
            if is_eos:
                flags |= FLAG_IS_EOS
            if not no_fb:
                flags |= FLAG_HAS_FEEDBACK
            cand_entries = [(code, CAND_SELECTED | CAND_RETAINED),
                            (dec.get("raw_top1", code), CAND_RAW_TOP1)]
            if AUDIO_EOS_CODE not in (c[0] for c in cand_entries):
                cand_entries.append((AUDIO_EOS_CODE, CAND_EOS))
            cand_entries = [(c, (f | CAND_EOS) if c == AUDIO_EOS_CODE else f)
                            for (c, f) in cand_entries]
            step = {
                "condition_id": cond["condition_id"],
                "global_step": global_step,
                "chunk_id": chunk["chunk_id"],
                "chunk_step": chunk_step,
                "decision_position": n_past,
                "n_past_before_feedback": n_past,
                "n_past_after_feedback": n_past if no_fb else n_past + 1,
                "previous_code": prev_code,
                "selected_code": code,
                "selected_token_id": 151687 + code,
                "raw_top1_code": dec.get("raw_top1", code),
                "candidate_offset": cand_count,
                "flags": flags,
                "candidate_count": len(cand_entries),
                "rng_state_digest": 0x12345678ABCDEF00 + global_step,
            }
            steps.append(step)
            hidden.extend(_float_row(1.0 + global_step * 0.01))
            if no_fb:
                feedback.extend(b"\x00" * TENSOR_ROW_BYTES)
            else:
                feedback.extend(_float_row(2.0 + code * 1e-4))
            for cand_code, cand_flags in cand_entries:
                candidates.extend(struct.pack("<ifI", cand_code,
                                              -0.5 if cand_code == code else -1.5,
                                              cand_flags))
                cand_count += 1
            prev_code = code
            global_step += 1
            first_overall = False
            if not no_fb:
                n_past += 1
        base = n_past

    cond_bytes = bytearray(_header(MAGIC_CONDITIONS, CONDITION_RECORD_BYTES, len(conditions)))
    for cond in conditions:
        _append_u64(cond_bytes, cond["condition_id"])
        _append_u32(cond_bytes, cond["chunk_id"])
        _append_i32(cond_bytes, cond["src_cnt_min"])
        _append_i32(cond_bytes, cond["src_cnt_max"])
        _append_i32(cond_bytes, cond["prefill_base_position"])
        _append_u64(cond_bytes, cond["row_offset"])
        _append_u32(cond_bytes, cond["text_row_count"])
        _append_u32(cond_bytes, cond["row_count"])
        _append_u32(cond_bytes, cond["text_eos_row_crc32"])
        _append_u32(cond_bytes, cond["audio_bos_row_crc32"])
        cond_bytes.append(cond["text_eos_count"])
        cond_bytes.append(cond["audio_bos_count"])
        cond_bytes.append(1 if cond["is_end_of_turn"] else 0)
        cond_bytes.append(0)
        _append_u64(cond_bytes, 0)
        _append_u32(cond_bytes, 0)
    cond_bytes.extend(rows)

    steps_bytes = bytearray(_header(MAGIC_STEPS, STEP_RECORD_BYTES, len(steps)))
    for step in steps:
        _append_u64(steps_bytes, step["condition_id"])
        _append_u64(steps_bytes, step["global_step"])
        _append_u32(steps_bytes, step["chunk_id"])
        _append_u32(steps_bytes, step["chunk_step"])
        _append_i32(steps_bytes, step["decision_position"])
        _append_i32(steps_bytes, step["n_past_before_feedback"])
        _append_i32(steps_bytes, step["n_past_after_feedback"])
        _append_i32(steps_bytes, step["previous_code"])
        _append_i32(steps_bytes, step["selected_code"])
        _append_i32(steps_bytes, step["selected_token_id"])
        _append_i32(steps_bytes, step["raw_top1_code"])
        _append_u64(steps_bytes, step["candidate_offset"])
        _append_u32(steps_bytes, step["flags"])
        _append_u32(steps_bytes, step["candidate_count"])
        _append_u64(steps_bytes, step["rng_state_digest"])
        _append_u64(steps_bytes, 0)

    files = {
        "conditions.bin": bytes(cond_bytes),
        "steps.bin": bytes(steps_bytes),
        "hidden.f32": _header(MAGIC_HIDDEN, TENSOR_ROW_BYTES, len(steps)) + bytes(hidden),
        "feedback.f32": _header(MAGIC_FEEDBACK, TENSOR_ROW_BYTES, len(steps)) + bytes(feedback),
        "candidates.bin": _header(MAGIC_CANDIDATES, CANDIDATE_RECORD_BYTES, cand_count) + bytes(candidates),
    }

    manifest = {
        "schema": SCHEMA,
        "endianness": "little",
        "complete": complete,
        "end_reason": end_reason,
        "sequence_id": 1,
        "request_generation": request_generation,
        "turn_id": turn_id,
        "media_type": media_type,
        "duplex_mode": duplex,
        "hidden_width": HIDDEN_WIDTH,
        "audio_vocab": AUDIO_VOCAB,
        "audio_bos_token_id": 151687,
        "audio_eos_code": AUDIO_EOS_CODE,
        "condition_count": len(conditions),
        "condition_row_count": len(rows) // TENSOR_ROW_BYTES,
        "step_count": len(steps),
        "candidate_count": cand_count,
        "record_layout": {
            "header_bytes": HEADER_BYTES,
            "condition_record_bytes": CONDITION_RECORD_BYTES,
            "step_record_bytes": STEP_RECORD_BYTES,
            "tensor_row_bytes": TENSOR_ROW_BYTES,
            "candidate_record_bytes": CANDIDATE_RECORD_BYTES,
            "condition_row_offset_units": "rows",
        },
        "candidate_flags": {
            "raw_top1": CAND_RAW_TOP1, "selected": CAND_SELECTED,
            "eos": CAND_EOS, "retained": CAND_RETAINED, "masked": CAND_MASKED,
        },
        "sampler": {"temperature": 0.8, "top_p": 0.85, "top_k": 25,
                    "repetition_penalty": 1.05, "repetition_window": 16,
                    "min_keep": 3},
        "files": {},
    }
    for name, blob in files.items():
        manifest["files"][name] = {
            "bytes": len(blob), "count": len(steps) if name in ("steps.bin", "hidden.f32", "feedback.f32")
            else (len(conditions) if name == "conditions.bin" else cand_count),
            "crc32": zlib.crc32(blob) & 0xFFFFFFFF,
        }

    if corrupt == "truncate_steps":
        files["steps.bin"] = files["steps.bin"][:-4]
        manifest["files"]["steps.bin"]["bytes"] -= 4
    elif corrupt == "crc_mismatch":
        manifest["files"]["hidden.f32"]["crc32"] ^= 0xFF
    elif corrupt == "nan_hidden":
        blob = bytearray(files["hidden.f32"])
        struct.pack_into("<f", blob, HEADER_BYTES + 4, float("nan"))
        files["hidden.f32"] = bytes(blob)
        manifest["files"]["hidden.f32"]["crc32"] = zlib.crc32(files["hidden.f32"]) & 0xFFFFFFFF
    elif corrupt == "bad_code":
        for i in range(len(steps)):
            off = HEADER_BYTES + i * STEP_RECORD_BYTES + 40  # selected_code
            struct.pack_into("<i", steps_bytes, off, 99000)
        files["steps.bin"] = bytes(steps_bytes)
        manifest["files"]["steps.bin"]["crc32"] = zlib.crc32(files["steps.bin"]) & 0xFFFFFFFF
    elif corrupt == "broken_condition_ref":
        for i in range(0, len(steps)):
            off = HEADER_BYTES + i * STEP_RECORD_BYTES
            struct.pack_into("<Q", steps_bytes, off, 999)
        files["steps.bin"] = bytes(steps_bytes)
        manifest["files"]["steps.bin"]["crc32"] = zlib.crc32(files["steps.bin"]) & 0xFFFFFFFF
    elif corrupt == "missing_manifest":
        for name, blob in files.items():
            (path / name).write_bytes(blob)
        return path
    elif corrupt == "duplicate_bos":
        # Rewrite the first condition claiming two audio BOS rows.
        struct.pack_into("<B", cond_bytes, HEADER_BYTES + 49, 2)
        files["conditions.bin"] = bytes(cond_bytes)
        manifest["files"]["conditions.bin"]["crc32"] = zlib.crc32(files["conditions.bin"]) & 0xFFFFFFFF

    # Position discontinuity / n_past mismatch corrupt the second step's
    # decision position in a second pass below.
    for name, blob in files.items():
        (path / name).write_bytes(blob)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return path, manifest


def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="talker_rollout_selftest_"))
    passed = 0
    failed = 0
    try:
        base_spec = [
            {"chunk_id": 0, "text_rows": 2, "is_end_of_turn": False,
             "decisions": [{"code": 11}, {"code": 12}, {"code": 13}]},
            {"chunk_id": 1, "text_rows": 1, "is_end_of_turn": False,
             "decisions": [{"code": 20}, {"code": 21}]},
            {"chunk_id": 2, "text_rows": 0, "is_end_of_turn": True,
             "decisions": [{"code": AUDIO_EOS_CODE, "is_eos": True, "no_feedback": False}]},
        ]

        def expect_ok(name, spec, **kw):
            nonlocal passed, failed
            seq_dir = tmp / ("ok_" + name)
            write_sequence(seq_dir, steps_spec=spec, **kw)
            try:
                validate_sequence(seq_dir)
                passed += 1
                print("  PASS  %s" % name)
            except ValidationError as exc:
                failed += 1
                print("  FAIL  %s: unexpectedly rejected: %s" % (name, exc))

        def expect_reject(name, spec=None, corrupt=None, mutate=None, **kw):
            nonlocal passed, failed
            seq_dir = tmp / ("bad_" + name)
            result = write_sequence(seq_dir, steps_spec=spec if spec is not None else base_spec,
                                    corrupt=corrupt, **kw)
            if mutate is not None:
                mutate(seq_dir)
            try:
                validate_sequence(seq_dir)
                failed += 1
                print("  FAIL  %s: unexpectedly accepted" % name)
            except ValidationError:
                passed += 1
                print("  PASS  %s (rejected)" % name)

        expect_ok("valid_multi_chunk", base_spec)
        expect_ok("valid_no_feedback_eos", [
            {"chunk_id": 0, "text_rows": 1, "is_end_of_turn": True,
             "decisions": [{"code": 5}, {"code": AUDIO_EOS_CODE, "is_eos": True, "no_feedback": True}]},
        ])
        expect_ok("incomplete_zero_steps", [], complete=False, end_reason="interrupted")

        expect_reject("truncated_steps", corrupt="truncate_steps")
        expect_reject("crc_mismatch", corrupt="crc_mismatch")
        expect_reject("nan_hidden", corrupt="nan_hidden")
        expect_reject("code_out_of_range", corrupt="bad_code")
        expect_reject("broken_condition_ref", corrupt="broken_condition_ref")
        expect_reject("missing_manifest", corrupt="missing_manifest")
        expect_reject("duplicate_bos", corrupt="duplicate_bos")

        def bump_position(seq_dir):
            data = bytearray((seq_dir / "steps.bin").read_bytes())
            # decision_position of step 1 sits at record offset 24.
            struct.pack_into("<i", data, HEADER_BYTES + STEP_RECORD_BYTES + 24, 12345)
            (seq_dir / "steps.bin").write_bytes(bytes(data))
            _patch_manifest_crc(seq_dir, "steps.bin", bytes(data))

        expect_reject("position_discontinuity", mutate=bump_position)

        def bump_n_past(seq_dir):
            data = bytearray((seq_dir / "steps.bin").read_bytes())
            # n_past_after_feedback of step 0 sits at record offset 32.
            struct.pack_into("<i", data, HEADER_BYTES + 32, 777)
            (seq_dir / "steps.bin").write_bytes(bytes(data))
            _patch_manifest_crc(seq_dir, "steps.bin", bytes(data))

        expect_reject("n_past_mismatch", mutate=bump_n_past)

        expect_reject("invalid_eos_feedback", spec=[
            {"chunk_id": 0, "text_rows": 1, "is_end_of_turn": True,
             "decisions": [{"code": 5, "no_feedback": True}]},  # non-EOS without feedback
        ])

        expect_reject("complete_zero_steps", spec=[], complete=True, end_reason="turn_complete")

        # Split leakage: two sequences sharing a content digest must not cross.
        root = tmp / "dataset"
        for turn in (1, 2, 3, 4):
            write_sequence(root / ("sequence_%08u_g1_t%d" % (turn, turn)), steps_spec=base_spec,
                           turn_id=turn)
        dup_src = root / "sequence_00000005_g1_t5"
        # t5 duplicates t1's content exactly (same digest, different turn).
        shutil.copytree(root / "sequence_00000001_g1_t1", dup_src)
        m = json.loads((dup_src / "manifest.json").read_text())
        m["turn_id"] = 5
        (dup_src / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")

        split_path = tmp / "split_manifest.json"
        result = split_dataset(root, split_path, ratio=0.75, seed=20260827, digest_group=True)
        names_train = {e["sequence"] for e in result["train"]}
        names_held = {e["sequence"] for e in result["held_out"]}
        digests_train = {e["content_digest"] for e in result["train"]}
        digests_held = {e["content_digest"] for e in result["held_out"]}
        if names_train & names_held:
            failed += 1
            print("  FAIL  split_leakage: sequences in both splits")
        elif digests_train & digests_held:
            failed += 1
            print("  FAIL  split_leakage: digest group crossed splits")
        else:
            passed += 1
            print("  PASS  split_leakage (digest groups kept together)")

        print("\nselftest: %d passed, %d failed (tmp: %s)" % (passed, failed, tmp))
        return 0 if failed == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _patch_manifest_crc(seq_dir, name, data):
    manifest = json.loads((seq_dir / "manifest.json").read_text())
    manifest["files"][name]["crc32"] = zlib.crc32(data) & 0xFFFFFFFF
    manifest["files"][name]["bytes"] = len(data)
    (seq_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="strictly validate one sequence dir")
    p_validate.add_argument("sequence_dir")
    p_validate.add_argument("--require-complete", action="store_true",
                            help="reject sequences not marked complete")

    p_summary = sub.add_parser("summary", help="validate and summarize a dataset root")
    p_summary.add_argument("root")

    p_split = sub.add_parser("split", help="deterministic grouped train/held-out split")
    p_split.add_argument("root")
    p_split.add_argument("--out", required=True)
    p_split.add_argument("--ratio", type=float, default=0.9)
    p_split.add_argument("--seed", type=int, default=20260827)
    p_split.add_argument("--digest-group", action="store_true",
                         help="keep identical-content sequences in the same split")

    sub.add_parser("selftest", help="synthetic validation/split tests")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate_sequence(Path(args.sequence_dir), require_complete=args.require_complete)
            print("OK %s" % args.sequence_dir)
            return 0
        if args.command == "summary":
            summary = summarize(args.root)
            print(json.dumps(summary, indent=2))
            return 0 if not summary["failures"] else 1
        if args.command == "split":
            result = split_dataset(args.root, args.out, args.ratio, args.seed, args.digest_group)
            print("split: %d train, %d held out, %d groups -> %s"
                  % (len(result["train"]), len(result["held_out"]),
                     result["group_count"], args.out))
            return 0
        if args.command == "selftest":
            return selftest()
    except ValidationError as exc:
        print("INVALID: %s" % exc, file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
