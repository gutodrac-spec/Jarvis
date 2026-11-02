"""Cria um modelo BERT minúsculo (pesos aleatórios) em locais/tiny para testar /modelo sem baixar nada."""
import sys
from pathlib import Path

from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

destino = Path(sys.argv[1])
destino.mkdir(parents=True, exist_ok=True)
vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "bom", "ruim", "filme", "o", "é"]
(destino / "vocab.txt").write_text("\n".join(vocab))
BertTokenizerFast(vocab_file=str(destino / "vocab.txt")).save_pretrained(destino)
cfg = BertConfig(vocab_size=len(vocab), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                 intermediate_size=32, num_labels=2, id2label={0: "NEGATIVO", 1: "POSITIVO"},
                 label2id={"NEGATIVO": 0, "POSITIVO": 1})
BertForSequenceClassification(cfg).save_pretrained(destino)
print("modelo tiny criado em", destino)
