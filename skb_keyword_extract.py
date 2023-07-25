from keybert import KeyBERT
from transformers import BertModel
import configparser

config = configparser.ConfigParser()
config.read('conf.ini')

KW_MODEL = config['KEYWORD']['model_name']

model = BertModel.from_pretrained(KW_MODEL)
kw_model = KeyBERT(model)


def keyword_extract(description):
    text = description
    keywords_mmr = kw_model.extract_keywords(text, keyphrase_ngram_range=(2, 10), use_mmr=True, top_n=15, diversity=0.8)
    print("---------------------------------------------")
    print("keywords")
    print("---------------------------------------------")

    print(keywords_mmr)
    return keywords_mmr

