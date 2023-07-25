import slack
import configparser

config = configparser.ConfigParser()
config.read('conf.ini')

SLACK_JIRA_URL = config['SLACK']['jira_url']
SLACK_TOKEN = config['SLACK']['token']
SLACK_CHANNEL = config['SLACK']['channel']


def slack_alarm(issueName, description):
    url = SLACK_JIRA_URL + issueName
    fileName = issueName + ".csv"
    message = issueName + "\n " + description + "\n" + url
    client = slack.WebClient(token=SLACK_TOKEN)
    response = client.files_upload(
        channels=SLACK_CHANNEL,
        file=fileName,
        initial_comment=message,
    )
