# 개발 내용

- 로그 추출 업무 처리 자동화

# 개발 내용의 의의

- 단순 사용 미숙으로 인한 업무 요청
- 데이터 추출의 경우 2~3일의 소요 시간 발생
- 데이터 추출 요청이 오후 6~7 시 이후 많이 올라옴

|클러스터| 검색 방식 |샘플 데이터 개수 |소요 시간(초)| TPS| 1억개의 데이터 처리 시 예상 시간|
|-|-|-|-|-|-|
|ooo 네비로그 클러스터 |Search After |5,066,384 |551.3 |9194| 3시간 1분

# 선택한 개발 방법 및 이유

![image](https://github.com/min9805/min9805.github.io/assets/56664567/08d5f389-9029-4d41-ab02-096443e85185)

1. JIRA 이슈 PULL
2. 이슈의 설명에서 키워드 추출
3. 추출된 키워드들을 텍스트 분류
4. 분류값을 바탕으로 쿼리 생성
5. JIRA Comment 생성

## 상세

```
매니저님 안녕하세요,

ooo팀 ooo입니다.


다름 아니라, KIBANA 통해 [YouTube 사용자 추출요청] 드릴 수 있을까요?

키바나가 익숙하지 않아 매니저님께 요청드리게 되었습니다.

(EUXP 내 편성 메뉴id로 추출했을 떄 아래와 같은데, 검증 부탁드릴 수 있을지요?)


요청 내용 : [o oo 내 ooooooo 사용자] (unique STB 수, Monthly)
(기존 추출 내역 ) : http://...........
log_time per month     Count     Unique count 
2022-11-01    00,000,000    000,000
2022-12-01    00,000,000    000,000
2023-01-01    00,000,000    000,000
데이터 업데이트 할 수 있도록 대시보드 생성 도움주실 수 있을까요?


더 필요하신 부분 있으시다면 편하게 말씀 부탁드립니다!


감사합니다.
```

- 핵심은 Text to Query
  - LLM 모델, OpenAi API 배제
  - 요청서를 제한하지 않고 기존의 요청서에서도 작동하게 하기 위해서 자연어 처리
  - 요청서에서 실제 데이터 추출을 위해 필요한 정보는 소수이기 때문에 키워드 추출
  - 해당 키워드들이 어떤 쿼리에 해당하는 지 정의하기 위해 텍스트 분류

결국 Text to Query 를 키워드 추출, 텍스트 분류 두 단계로 진행

# 현재 진행 상황

## 1. JIRA 이슈 PULL

```
query_params = {
    "jql": "project = a AND component = b AND status != c AND status != d",
    "fields": "summary, description",
    "maxResults": 1,
    "startAt": 0
}
```

```
scheduler.add_job(log_extract_automation, CronTrigger(hour=10))
scheduler.add_job(log_extract_automation, CronTrigger(hour=20))
```

- [a] 프로젝트에서 [b] 구성요소를 가지고 있으며 [c], [d] 상태가 아닌 이슈들을 PULL
- Python apscheduler 를 사용해 오전 10시, 오후 8시 이슈 PULL

## 2. 이슈의 설명에서 키워드 추출

```
model = BertModel.from_pretrained(klue/bert-base)
kw_model = KeyBERT(model)
```

- 키워드 추출을 위해 "KeyBERT" 를 사용하였고 이를 위해 "klue" 모델을 사용
  - KeyBert : 키워드 추출에 특화된 오픈소스 파이썬 라이브러리, 이미 pretrain 되어있기에 모델 구축보다 적은 데이터 셋으로 튜닝 가능
  - klue : KeyBert 에 들어가는 pretrain 된 모델
- 키워드 추출 시 일정 중요도 이상의 키워드들만 텍스트 분류

## 3. 추출된 키워드들을 텍스트 분류

```
model = AutoModelForSequenceClassification.from_pretrained(TC_MODEL)
tokenizer = AutoTokenizer.from_pretrained(TC_MODEL)
```

- fine-tuning 한 모델을 사용
  - https://huggingface.co/min9805/bert-base-finetuned-ynat

## 4. 분류값을 바탕으로 쿼리 생성

```
"0": "action_id:action_a",
"1": "action_id:action_b",
"2": "action_id:action_c",
"3": "page_id:page_a",
"4": "action_body.result:result_a",
"5": "action_body.result:result_b"
```

- 각 분류 값에 대해서 필요한 쿼리를 미리 작성
- 이후 쿼리 생성 부분에서 해당 내용 삽입
- 요청서의 양식에 따라 대상, 기간, 필드는 정규식으로 추출해서 쿼리에 삽입

```
[추출 개요] 

...

[목적]

...

[대상 및 기간]

대상 : ooo-oooo

기간 : 2023-01-01 ~ 2023-07-25

필드 : a, b, c, d
```

## 5. JIRA Comment 생성 -> Slack 알림 생성

- 생성된 쿼리를 통해 ES 에서 데이터 추출 및 CSV 파일 생성
- 해당 파일과 함께 Slack 알림 생성

# 결과

- JIRA 에 이슈가 올라오면 정해진 시간에 감시 후 일련의 과정에 따라 데이터 추출 후 Slack 알림 생성
- 데이터 추출에서 키워드 추출이 잘 이루어지지 않는다.
  - 일반 문장을 기반으로 텍스트 분류하는 게 낫다.
- 훈련 데이터 셋이 빈약하기도하고 데이터 셋 자체에서 라벨의 분류가 잘 보이지 않음

# 사후 검토 및 회고

## 1. JIRA 이슈 PULL

- 현재 JIRA 이슈 댓글에 대해서도 추출 및 처리 필요
- 상위 1개의 이슈에 대해서 추출하기에 시간대에 따른 추가 로직 필요
- 추출서 양식의 예외 처리

## 2. 이슈의 설명에서 키워드 추출

- 키워드 추출에 대한 Fine-tuning 필요
- 키워드 추출에 대한 파라미터 테스트 및 필터링할 중요도 설정

## 3. 추출된 키워드들을 텍스트 분류

- 텍스트 분류에 대한 Fine-tuning 필요
- 모든 쿼리를 학습 불가능
  - 기존에는 키워드로 필요한 필드만 추출해내고 조건은 해당 키워드에서 다시 추출하려했음
    ex) "result_a에 진입한 ... " -> 0 : "action_body_result" -> action_body_result = "result_a"
- 텍스트 분류 시 일정한 분류값에 대해서 필터링 필요

## 4. 분류값을 바탕으로 쿼리 생성

- 추출하는 값과 집계하는 값

## 5. JIRA Comment 생성 -> Slack 알림 생성

- Slack 에 interactive message 를 사용해 jira 에 댓글 업로드

---

- 처음 정의해놓는 것들이 확실하고 자세할 수록 좋다 (아키텍처, 플로우 ... )
- 일정 세분화를 통해 현재 진행상황을 파악
- 요청서를 자유롭게 두고 싶었지만 요청서 규격을 정의하는 것이 요청하는 입장과 받는 입장 모두에게 편하다
  - form 으로 데이터 받아서 처리

> 모델은 클롤링이 가능하거나 데이터 셋이 많을 때 사용하자. <br> 버전 관리를 잘하자..
