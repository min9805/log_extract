import http.client
import urllib.parse
import json
import csv
from bs4 import BeautifulSoup
from elasticsearch import Elasticsearch
import configparser
import re
from datetime import datetime, date
from jira import JIRA
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import skb_keyword_extract
import skb_text_classify
import skb_slack

KEYWORD_CONST = 0.4

config = configparser.ConfigParser()
config.read('conf.ini')

JIRA_URL = config['JIRA']['url']
JIRA_TOKEN = config['JIRA']['token']
JIRA_TEST_URL = config['JIRA']['test_url']
JIRA_TEST_TOKEN = config['JIRA']['test_token']
JIRA_TEST_USER = config['JIRA']['test_user']

TC_FILENAME = config['TEXT_CLASSIFY']['mapping_file_name']

ES_URL = config['ELASTIC_SEARCH']['url']
ES_USERNAME = config['ELASTIC_SEARCH']['username']
ES_PASSWORD = config['ELASTIC_SEARCH']['password']
ES_INDEX = config['ELASTIC_SEARCH']['index']

es = Elasticsearch(ES_URL, http_auth=(ES_USERNAME, ES_PASSWORD))


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
    return jira_description, html_data["issues"][0]["key"], html_data["issues"][0]["fields"]["summary"]


def jira_pull_test():
    options = {
        'server': JIRA_TEST_URL
    }

    jira = JIRA(options, basic_auth=(JIRA_TEST_USER, JIRA_TEST_TOKEN))

    project_key = 'LD'

    jql_query = f'project = "{project_key}"'
    issues = jira.search_issues(jql_query, maxResults=1)
    return issues[0].fields.description, issues[0].key, issues[0].fields.summary


def extract_form_data(text):
    target_match = re.search(r"대상\s*:\s*(.*?)\s*\n", text)
    period_match = re.search(r"기간\s*:\s*(.*?)\s*~\s*(.*?)\s*\n", text)
    field_match = re.search(r"필드\s*:\s*(.*?)\s*\n", text)

    target = target_match.group(1).strip() if target_match else None
    start_date, end_date = period_match.groups() if period_match else (None, None)
    field = field_match.group(1).strip() if field_match else None

    targets = [t.strip() for t in target.split(',')] if target else []
    fields = [f.strip() for f in field.split(',')] if field else []

    start_date = str(start_date) + "T00:00:00.000Z"
    if end_date == str(date.today()):
        end_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        end_date = str(end_date) + "T00:00:00.000Z"

    return {"target": targets, "start_date": start_date, "end_date": end_date, "fields": fields}


def make_query(text_classify_list, form_data):
    kql = []

    with open(TC_FILENAME, 'r') as f:
        loaded_mapping_dict = json.load(f)

    for r in text_classify_list:
        print(loaded_mapping_dict[str(r[1])])

        kql.append(loaded_mapping_dict[str(r[1])])
    query = {
        "size": 10000,
        "sort": ["_doc"],
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

    query["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] = form_data["start_date"]
    query["query"]["bool"]["filter"][0]["range"]["@timestamp"]["lte"] = form_data["end_date"]

    return query


def extract_csv(columns, index_name, query, issue_name):
    csv_filename = issue_name + ".csv"
    csv_file = open(csv_filename, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)

    csv_writer.writerow(columns)

    def run_search(kql):
        return es.search(index=index_name, body=kql)

    def write_to_csv(hits):
        for hit in hits:
            source_data = hit.get('_source', {})
            row = [source_data.get(column, '') for column in columns]
            csv_writer.writerow(row)

    def paginate_search(paginate_query):
        initial_result = run_search(paginate_query)
        print(initial_result)

        hits = initial_result['hits']['hits']
        write_to_csv(initial_result['hits']['hits'])

        while hits:
            last_sort_values = hits[-1]['sort']
            paginate_query['search_after'] = last_sort_values

            next_result = run_search(paginate_query)
            print(next_result)

            write_to_csv(next_result['hits']['hits'])

            hits = next_result['hits']['hits']

        csv_file.close()

    paginate_search(query)


def log_extract_automation():
    # JIRA 에서 데이터 PULL
    data_dict = jira_pull()
    desc, data_key, data_summary = html_parser(data_dict)
    form_data = extract_form_data(desc)
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
    kibana_query = make_query(classify, form_data)
    print("---------------------------------------------")
    print("make query")
    print("---------------------------------------------")
    print(kibana_query)
    column_name = ["stb_mac", "device_model", "page_type", "action_id", "@timestamp"]
    # 생성된 쿼리로 csv 추출
    extract_csv(column_name, ES_INDEX, kibana_query, data_key)
    # 완료 시 slack 알림 생성
    skb_slack.slack_alarm(data_key, data_summary)


if __name__ == '__main__':
    scheduler = BlockingScheduler()

    # 오전 10시와 오후 4시에 실행하는 스케줄 등록
    scheduler.add_job(log_extract_automation, CronTrigger(hour=10))
    scheduler.add_job(log_extract_automation, CronTrigger(hour=16))

    try:
        print('Scheduler started.')
        scheduler.start()
    except KeyboardInterrupt:
        print('Batch scheduler stopped.')
