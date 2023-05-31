import os
import http.client
import json
from urllib.parse import urlparse
import datetime

status_colors_and_message = {
    "ALARM": {"color": "danger", "message": "위험"},
    "INSUFFICIENT_DATA": {"color": "warning", "message": "데이터 부족"},
    "OK": {"color": "good", "message": "정상"}
}

comparison_operator = {
    "GreaterThanOrEqualToThreshold": ">=",
    "GreaterThanThreshold": ">",
    "LowerThanOrEqualToThreshold": "<=",
    "LessThanThreshold": "<",
}

def process_event(event, webhook):
    sns_message = event["Records"][0]["Sns"]["Message"]
    post_data = build_slack_message(json.loads(sns_message))
    post_slack(post_data, webhook)

def build_slack_message(data):
    new_state = status_colors_and_message[data["NewStateValue"]]
    old_state = status_colors_and_message[data["OldStateValue"]]
    execute_time = to_yyyymmddhhmmss(data["StateChangeTime"])
    description = data["AlarmDescription"]
    cause = get_cause(data)

    return {
        "attachments": [
            {
                "title": f"[{data['AlarmName']}]",
                "color": new_state["color"],
                "fields": [
                    {
                        "title": "언제",
                        "value": execute_time
                    },
                    {
                        "title": "설명",
                        "value": description
                    },
                    {
                        "title": "원인",
                        "value": cause
                    },
                    {
                        "title": "이전 상태",
                        "value": old_state["message"],
                        "short": True
                    },
                    {
                        "title": "현재 상태",
                        "value": f"*{new_state['message']}*",
                        "short": True
                    },
                    {
                        "title": "바로가기",
                        "value": create_link(data)
                    }
                ]
            }
        ]
    }

def create_link(data):
    alarm_arn = data["AlarmArn"]
    region_code = export_region_code(alarm_arn)
    alarm_name_encoded = urlparse(data["AlarmName"]).geturl()
    return f"https://console.aws.amazon.com/cloudwatch/home?region={region_code}#alarm:alarmFilter=ANY;name={alarm_name_encoded}"

def export_region_code(arn):
    return arn.replace("arn:aws:cloudwatch:", "").split(":")[0]

def get_cause(data):
    trigger = data["Trigger"]
    evaluation_periods = trigger["EvaluationPeriods"]
    minutes = trigger["Period"] // 60

    if "Metrics" in data["Trigger"]:
        return build_anomaly_detection_band(data, evaluation_periods, minutes)

    return build_threshold_message(data, evaluation_periods, minutes)

def build_anomaly_detection_band(data, evaluation_periods, minutes):
    metrics = data["Trigger"]["Metrics"]
    metric = next(metric["Id"] for metric in metrics if metric["Id"] == "m1")["MetricStat"]["Metric"]["MetricName"]
    expression = next(metric["Expression"] for metric in metrics if metric["Id"] == "ad1")["Expression"]
    width = expression.split(",")[1].replace(")", "").strip()

    return f"{evaluation_periods * minutes} 분 동안 {evaluation_periods} 회 {metric} 지표가 범위(약 {width}배)를 벗어났습니다."

def build_threshold_message(data, evaluation_periods, minutes):
    trigger = data["Trigger"]
    threshold = trigger["Threshold"]
    metric = trigger["MetricName"]
    operator = comparison_operator[trigger["ComparisonOperator"]]

    return f"{evaluation_periods * minutes} 분 동안 {evaluation_periods} 회 {metric} {operator} {threshold}"

def to_yyyymmddhhmmss(time_string):
    if not time_string:
        return ""

    kst_date = (datetime.datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%S.%f%z") + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")

    return kst_date

def post_slack(message, slack_url):
    url = urlparse(slack_url)
    conn = http.client.HTTPSConnection(url.netloc)
    headers = {"Content-Type": "application/json"}

    conn.request("POST", url.path, json.dumps(message), headers)
    response = conn.getresponse()

    return response.read().decode()

def lambda_handler(event, context):
    webhook = os.environ.get("webhook")
    if not webhook:
        raise ValueError("Missing environment variable: webhook")

    process_event(event, webhook)
