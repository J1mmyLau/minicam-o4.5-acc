<!--
  BRANCH: fix/ws-multimodal-nan
  STATUS: COMPLETE
-->

# fix/ws-multimodal-nan

> WS multimodal NaN investigation. Audio/video paths produce all-NaN logits. NaN traced through whisper_input_mel→whisper_embed_output→audio_embed_memcpy→audio_only_prefill→logits_ith. OMNI_NAN_DIAG instrumentation added.

