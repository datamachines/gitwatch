#!/usr/bin/python
# Gitwatch
# Apache License v2
# https://github.com/datamachines/gitwatch
from __future__ import print_function
import git
from datetime import datetime
import yaml
import re
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

configfile = sys.argv[1]
nerf = sys.argv[2]
runfile = "runfile.yaml"

# Set up configuraiton
conf = yaml.safe_load(open(configfile))
repo = git.Repo(conf['repo_dir'])

# now is a time that is only read once at the beginning of program execution.
# Since it is later written to the runfile, we want to keep it as atomic
# as possible.
now = datetime.now()

# logtime is read just prior to most log messages and is used to tag log output
logtime = datetime.now().isoformat()
print(logtime, "Initialized. Now:", int(now.strftime("%s")))

# writes our runfile to disk.
# TODO: write a test mode so we can ensure the filesystem is writable before.
# going into the rest of the program. That will account for the edge case that
# he filesystem state changes after Gitwatch is initially installed.
def write_runfile(run):
    try:
        with open(runfile, 'w') as outfile:
            outfile.write( yaml.dump(run, default_flow_style=False) )
    except IOError:
        logtime = datetime.now().isoformat()
        print(logtime, "ERROR - Unable to write runfile.")
        exit(1)

# This works with AWS SES
def send_smtp_email(email_to, email_subject, email_body):
    logtime = datetime.now().isoformat()
    num_recepients = len(email_to)
    if num_recepients > conf['smtp_max_recepients_per_email']:
        print(logtime, 'ERROR - Too many recepients.')
        return 0
    msg = MIMEText(email_body, 'html')
    msg['Subject'] = email_subject
    msg['From'] = conf['smtp_from']
    msg['To'] = ','.join(email_to)
    email_message = msg.as_string()
    try:
        smtp = smtplib.SMTP_SSL()
        smtp.connect(conf['smtp_server'],int(conf['smtp_port']))
        smtp.login(conf['smtp_username'], conf['smtp_password'])
        smtp.sendmail(conf['smtp_from'], email_to, email_message)
        smtp.close()
    except smtplib.SMTPConnectError:
        print(logtime, 'ERROR - Could not connect to SMTP server.')
        return 0
    except smtplib.SMTPAuthenticationError:
        print(logtime, 'ERROR - SMTP authentication error.')
        return 0
    return 1

# We try to read the runfile to get the last run time. If it doesn't exist
# we create one and exit cleanly.
try:
    run = yaml.safe_load(open(runfile))
except IOError:
    run = dict(lastrun = int(now.strftime("%s")))
    logtime = datetime.now().isoformat()
    print(logtime, "First run, just creating runfile and exiting.")
    print(logtime,
        "Tracking new commits from this moment in time:",
        now.isoformat())
    write_runfile(run)
    exit(0)

# Here, we grab anything that looks like an email address from the alert-list
# file in the repo.
try:
    ee = re.compile(("([a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`"
                    "{|}~-]+)*(@|\sat\s)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(\.|"
                    "\sdot\s))+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)"))
    with open(conf['repo_dir'] + conf['alert_file']) as afile:
        alert_file_text = afile.read().lower()
    emails = list(email[0] for email in re.findall(ee, alert_file_text))
except IOError:
    logtime = datetime.now().isoformat()
    print(logtime, "ERROR: Unable to read alert file.", conf['alert_file'])
    exit(1)
#print(emails)

print(logtime, "Last run:", run['lastrun'])

commits = list(repo.iter_commits('master'))
alert_queue = []

# Iterate through the commits sending email alerts for commits that have
# happened after the time recorded in our runtime file.
for i in range(0,len(commits)):
    commit = commits[i]
    if commit.committed_date > run['lastrun']:
        isodtg = datetime.utcfromtimestamp(commit.committed_date).isoformat()
        subject = conf['smtp_subject'] + " by " + commit.author.name
        body = "<html>\n" \
            + "The following files were modified:<br>\n"

        body += "\n\n<pre>\n" + repo.git.show(commits[i]) + "\n</pre>\n<br><br>"
        body += "<a href=\"" + conf['md_link_prefix'] + "\">" \
            + conf['md_link_prefix'] + "</a><br>\n"
        body += "<br>\nCommit: " + str(commit) + "<br>\n" \
            + "Timestamp: " + str(commit.committed_date) + "<br>\n" \
            + "</html>\n"
        #print("Body:",body)
        print("------------------")
        print("Commit:",commit)
        print("Subject:",subject)
        print("Commit timestamp:",commit.committed_date)
        print("Sending email to:", emails)
        send_smtp_email(emails, subject, body)
        #print(datetime.utcfromtimestamp(commit.committed_date).isoformat())

# Write the atomic time now to the runfile and then exit cleanly.
run['lastrun'] = int(now.strftime("%s"))
#TODO: Comment the next line to keep running with a specified runtime
# useful when testing, pick a runtime ecpoch that only has one commit after it.
write_runfile(run)
exit(0)
