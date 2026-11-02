"""Substituto do pacote `spaces` do Hugging Face (ZeroGPU), usado pelo executor.

Os Spaces ZeroGPU decoram as funções com @spaces.GPU. Aqui a GPU já é do Studio, então o decorador
só devolve a função como ela é, aceitando todas as formas de uso:
    @spaces.GPU   @spaces.GPU()   @spaces.GPU(duration=120)   @spaces.GPU(duration=f, size="xlarge")
"""


def GPU(*args, **kwargs):  # noqa: N802 (o nome é o do pacote original)
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def decorador(funcao):
        return funcao

    return decorador


def gradio_auto_wrap(funcao):
    """O Gradio chama isto quando acha que está num Space (SPACE_ID definido); aqui não há nada a embrulhar."""
    return funcao


def __getattr__(nome):
    raise AttributeError(
        f"spaces.{nome} não existe no executor. Spaces que dependem de compilação AoTI "
        "(spaces.aoti_*) são feitos para a GPU do ZeroGPU e não rodam aqui."
    )
