import json
import lxml.html
import os
import requests
from polling_bot.brain import SlackClient


# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///data.sqlite'
import scraperwiki


SEND_NOTIFICATIONS = True

try:
    SLACK_WEBHOOK_URL = os.environ['MORPH_UBUNTU_BOT_SLACK_WEBHOOK_URL']
except KeyError:
    SLACK_WEBHOOK_URL = None


def post_slack_message(release):
    message = "Found new Ubuntu {version} ({instance_type}) image in {zone}: `{ami_id}`".format(
        version=release['version'],
        instance_type=release['instance_type'],
        zone=release['zone'],
        ami_id=release['ami_id'],
    )
    slack = SlackClient(SLACK_WEBHOOK_URL)
    slack.post_message(message)


def init():
    scraperwiki.sql.execute("""
        CREATE TABLE IF NOT EXISTS data (
            version TEXT,
            date TEXT,
            zone TEXT,
            ami_id TEXT,
            instance_type TEXT);
    """)
    scraperwiki.sql.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        data_amiid_unique ON data (ami_id);
    """)


def scrape():
    res = requests.get('https://cloud-images.ubuntu.com/locator/ec2/releasesTable')
    if res.status_code != 200:
        res.raise_for_status()
    js = res.text

    # /releasesTable serves up js, not json
    # this hack strips the last trailing comma so it will parse as json
    # but it is probably going to break at some point
    data = json.loads(js[:-6] + ']}')

    for row in data['aaData']:
        link = lxml.html.fromstring(row[6])
        record = {
            'zone': row[0],
            'version': row[2],
            'instance_type': row[4],
            'date': row[5],
            'ami_id': link.text,
        }
        if record['zone'] in ['eu-west-1', 'eu-west-2'] and\
                record['version'] == '16.04 LTS' and\
                record['instance_type'] == 'hvm:ebs-ssd':

            exists = scraperwiki.sql.select(
                "* FROM 'data' WHERE ami_id=?", record['ami_id'])
            if len(exists) == 0:
                if SLACK_WEBHOOK_URL and SEND_NOTIFICATIONS:
                    print(record)
                    post_slack_message(record)

            scraperwiki.sqlite.save(
                unique_keys=['ami_id'], data=record, table_name='data')
            scraperwiki.sqlite.commit_transactions()


init()
scrape()