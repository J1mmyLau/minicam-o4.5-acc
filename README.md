<!--
  BRANCH: fix/full-duplex-request-max-tokens
  STATUS: COMPLETE
-->

# fix/full-duplex-request-max-tokens

> Fix full-duplex ws_handler never set request_max_tokens → n_ctx=0 default → max_tgt_len=0 → 0 tokens. Root cause of empty output in full-duplex mode. commit baee842.

