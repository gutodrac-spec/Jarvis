---
domain:
- multi-modal
tags:
- gradio
- huggingface
- spaces
- api
license: Apache License 2.0
deployspec:
  entry_file: app.py
---

# 🧩 Executor de Spaces e modelos do Hugging Face

API (Gradio) que carrega qualquer Space Gradio ou modelo do Hugging Face na GPU deste Studio.
Use pelo site que acompanha (`estudio/site/index.html`) ou por código:

```python
from gradio_client import Client
api = Client("https://SEU-USUARIO-NOME.ms.show")
api.predict("SUA_CHAVE", "Lightricks/ltx-video-distilled", api_name="/carregar")   # começa a carregar
api.predict(api_name="/status")                                                    # acompanhe até "pronto"
api.predict("SUA_CHAVE", "Lightricks/ltx-video-distilled", api_name="/apis")       # endpoints e parâmetros
```

Código: https://github.com/gutodrac-spec/Jarvis/tree/estudio-video/estudio/runner
