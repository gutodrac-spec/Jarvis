# Site do executor

Página única (`index.html`, sem build) que usa a API do executor (`../runner`) rodando na xGPU do Studio do ModelScope.
Hospede em qualquer lugar estático (Space estático do Hugging Face, GitHub Pages, Vercel, outro Studio estático) ou abra o arquivo direto no navegador.

1. Cole o endereço do Studio (`https://seu-usuario-nome.ms.show`) e a chave (`RUNNER_CHAVE`); clique **Conectar**.
2. **🔍 Testar GPU**: confirma que os Spaces enxergam a GPU (veja `../runner/PASSO_A_PASSO.md`).
3. **Space:** `dono/nome` → Carregar → o formulário do Space aparece sozinho → Executar.
4. **Modelo solto:** `dono/nome` + tarefa + entrada em JSON.

A chave e o endereço ficam só no seu navegador. O cliente Gradio vem do CDN (`@gradio/client@2.7.1`).
