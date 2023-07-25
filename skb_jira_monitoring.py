import http.client
import urllib.parse
import json
import requests
import csv
from bs4 import BeautifulSoup
import skb_keyword_extract
import skb_text_classify
import skb_slack
import configparser

KEYWORD_CONST = 0.4

config = configparser.ConfigParser()
config.read('conf.ini')

JIRA_URL = config['JIRA']['url']
JIRA_TOKEN = config['JIRA']['token']

TC_FILENAME = config['TEXT_CLASSIFY']['mapping_file_name']

ES_URL = config['ELASTIC_SEARCH']['url']
ES_USERNAME = config['ELASTIC_SEARCH']['username']
ES_PASSWORD = config['ELASTIC_SEARCH']['password']


def jira_pull():
    conn = http.client.HTTPSConnection(JIRA_URL)
    query_params = {
        "jql": "project = LOG AND component = 14940 AND status != 10805 AND status != 10304",
        "fields": "summary, description",
        "maxResults": 1,
        "startAt": 0
    }
    query_string = urllib.parse.urlencode(query_params)
    headers = {
        'Authorization': JIRA_TOKEN,
    }
    conn.request("GET", f"/rest/api/latest/search?{query_string}", body=None, headers=headers)
    res = conn.getresponse()
    jira_data = res.read()
    jira_data = jira_data.decode("utf-8")
    jira_data_dict = json.loads(jira_data)

    return jira_data_dict


def html_parser(html_data):
    description = html_data["issues"][0]["fields"]["description"]
    soup = BeautifulSoup(description, 'html.parser')
    jira_description = soup.get_text()
    return jira_description


def make_query(text_classify_list):
    kql = []

    with open(TC_FILENAME, 'r') as f:
        loaded_mapping_dict = json.load(f)

    for r in text_classify_list:
        print(loaded_mapping_dict[str(r[1])])

        kql.append(loaded_mapping_dict[str(r[1])])
    query = {
        "size": 1000,
        "query": {
            "bool": {
                "must": [
                ],
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-15d"
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
        }
    }
    kql_uni = list(set(kql))
    for q in kql_uni:
        field_name, field_value = q.split(":")
        query["query"]["bool"]["must"].append({"term": {field_name: field_value}})

    return query


def extract_csv(columns):
    response = requests.get(ES_URL, auth=(ES_USERNAME, ES_PASSWORD), json=kibana_query)
    if response.status_code == 200:
        data = response.json()
        hits = data.get('hits', {}).get('hits', [])

        # 결과를 CSV 파일로 저장
        csv_filename = data_dict["issues"][0]["key"] + ".csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow(columns)
            for hit in hits:
                source_data = hit.get('_source', {})
                row = []
                for column in columns:
                    row.append(source_data.get(column, ''))
                csv_writer.writerow(row)
        print("extract_csv")
    else:
        print(f"Error: {response.status_code} - {response.text}")


# JIRA 에서 데이터 PULL
data_dict = jira_pull()
desc = html_parser(data_dict)

print("---------------------------------------------")
print("data to text")
print("---------------------------------------------")
print(desc)

# JIRA issue 키워드 추출
keywords = skb_keyword_extract.keyword_extract(desc)
classify = []

# 각 키워드들에 대해서 텍스트 분류
for kw in keywords:
    if kw[1] > KEYWORD_CONST:
        classify.append((kw[0], skb_text_classify.text_classification(kw[0])))
    else:
        break

print("---------------------------------------------")
print("text classification result")
print("---------------------------------------------")
print(classify)

# 분류 결과값을 통해 쿼리 생성
kibana_query = make_query(classify)
print("---------------------------------------------")
print("make query")
print("---------------------------------------------")
print(kibana_query)

column_name = ["stb_id", "device_model"]

# 생성된 쿼리로 csv 추출
extract_csv(column_name)

# 완료 시 slack 알림 생성
skb_slack.slack_alarm(data_dict["issues"][0]["key"], data_dict["issues"][0]["fields"]["summary"])
