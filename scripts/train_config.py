import os

from deepspec.trainer import Qwen3DSparkTrainer


# Upstream configs at the pinned commit define these locally; there is no
# deepspec.utils.constant module to import them from.
BASE_TB_DIR = os.path.expanduser("~/tensorboard")
BASE_CKPT_DIR = os.path.expanduser("~/checkpoints")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


POOL_ROOT = os.environ.get("POOL_ROOT", "/pool/hdd/minicpmo-dspark")

# Target model that produced the cached hidden states.
TARGET = os.environ.get(
    "MINICPMO_MODEL_PATH", os.path.join(POOL_ROOT, "models", "MiniCPM-o-4_5")
)
# Draft weights this run continues from. The directory name records which
# upstream stage it came from; this config only ever calls it WARMSTART.
WARMSTART = os.environ.get(
    "DEEPSPEC_WARMSTART_DRAFT_PATH", os.path.join(POOL_ROOT, "warmstart", "stage10")
)

project_name = "deepspec"
exp_name = "dspark_block7_minicpmo_4_5_multimodal_dtriad_stage11_b300_dp8"
seed = 42

model = dict(
    target_model_name_or_path=TARGET,
    warmstart_draft_path=WARMSTART,
    block_size=7,
    num_draft_layers=5,
    target_layer_ids=[1, 9, 17, 25, 33],
    mask_token_id=151669,
    num_anchors=512,
    markov_rank=256,
    markov_head_type="vanilla",
    confidence_head_alpha=0.5,
    confidence_head_with_markov=True,
    loss_decay_gamma=8.0,
    ce_loss_alpha=0.1,
    l1_loss_alpha=0.9,
)

train = dict(
    trainer_cls=Qwen3DSparkTrainer,
    lr=3.0e-6,
    warmup_ratio=0.05,
    weight_decay=0.0,
    precision="bf16",
    local_batch_size=int(os.environ.get("LOCAL_BATCH_SIZE", "1")),
    global_batch_size=int(os.environ.get("GLOBAL_BATCH_SIZE", "32")),
    num_train_epochs=1,
    max_train_steps=int(os.environ.get("MAX_TRAIN_STEPS", "150")),
    max_grad_norm=1.0,
    sharding_strategy="no_shard",
    torch_compile=env_bool("TORCH_COMPILE", False),
)

logging = dict(logging_steps=1, checkpointing_steps=25)

data = dict(
    target_cache_path=None,
    chat_template="minicpmo_multimodal_rollout",
    max_length=2048,
    num_workers=4,
)


def finalize_cfg(cfg):
    logging_cfg = dict(cfg["logging"])
    logging_cfg["checkpoint_dir"] = os.path.join(
        BASE_CKPT_DIR, str(cfg["project_name"]), str(cfg["exp_name"])
    )
    logging_cfg["tensorboard_dir"] = os.path.join(
        BASE_TB_DIR, str(cfg["project_name"]), str(cfg["exp_name"])
    )
    cfg["logging"] = logging_cfg
    return cfg


# --opts overrides applied at save time
data['target_cache_path'] = '/pool/hdd/minicpmo-dspark/cache/minicpmo_dtriad3_media_fp16'
