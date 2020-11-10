import argparse
import datetime
import re
import ruamel.yaml
import socket
import xmltodict

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pymongo import MongoClient
from smtplib import SMTP

def main():
    with open(args.junitxml) as fd:
        host = socket.gethostname()
        doc = xmltodict.parse(fd.read())
        test_groups = {'total': int(doc['testsuites']['testsuite']['@tests']), 'clowder': 0, 'polyglot': 0, 'fence': 0}
        elapsed_time = float(doc['testsuites']['testsuite']['@time'])
        log = {'errors': list(), 'failures': list(), 'timeouts': list(), 'skipped': list(), 'success': list()}
        processing_timeout = int(args.processing_timeout)

        for testcase in doc['testsuites']['testsuite']['testcase']:
            # create log message
            logmsg = dict()
            logmsg['name'] = testcase['@name']
            logmsg['classname'] = testcase['@classname']
            logmsg['time'] = float(testcase['@time'])
            if 'error' in testcase:
                msgtype = 'errors'
                logmsg['message'] = testcase['error']['@message']
                logmsg['trace'] = testcase['error']['#text']
            elif 'failure' in testcase:
                # group as time outs if longer than processing_timeout
                logmsg['message'] = testcase['failure']['@message']
                logmsg['trace'] = testcase['failure']['#text']
                timeoutfailure = logmsg['message'].endswith('Timeout')
                if timeoutfailure:
                    msgtype = 'timeouts'
                else:
                    msgtype = 'failures'
            elif 'skipped' in testcase:
                msgtype = 'skipped'
                logmsg['message'] = testcase['skipped']['@message']
            else:
                msgtype = 'success'
            if 'system-out' in testcase:
                logmsg['system-out'] = testcase['system-out']
            if 'system-err' in testcase:
                logmsg['system-err'] = testcase['system-err']

            # cleanup of message, see also:
            # http://stackoverflow.com/questions/40012526/junitxml-and-pytest-difference-in-message-when-running-in-parallel
            if 'message' in logmsg:
                if 'AssertionError: ' in logmsg['message']:
                    logmsg['message'] = re.sub(r".*E +(AssertionError: .*) E +assert.*", r"\1", logmsg['message'])
                if 'HTTPError: ' in logmsg['message']:
                    logmsg['message'] = re.sub(r".*E +(HTTPError: .*) {2}[^ ]*: HTTPError.*", r"\1", logmsg['message'])
                if 'OSError: ' in logmsg['message']:
                    logmsg['message'] = re.sub(r".*E +(OSError: .*) {2}[^ ]*: OSError.*", r"\1", logmsg['message'])

            # hide some private information, combine array into string
            for key in logmsg:
                if isinstance(logmsg[key], list):
                    logmsg[key] = "\n".join(logmsg[key])
                if 'username' in str(logmsg[key]):
                    logmsg[key] = re.sub(r"username = '[^']*'", "username = 'username'", logmsg[key])
                if 'password' in str(logmsg[key]):
                    logmsg[key] = re.sub(r"password = '[^']*'", "password = 'password'", logmsg[key])
                if 'api_key' in str(logmsg[key]):
                    logmsg[key] = re.sub(r"api_key = '[^']*'", "api_key = 'api_key'", logmsg[key])
                if 'api_token' in str(logmsg[key]):
                    logmsg[key] = re.sub(r"api_token = '[^']*'", "api_token = 'api_token'", logmsg[key])

            # group tests failures/errors
            if msgtype == 'errors' or msgtype == 'failures' or msgtype == 'timeouts':
                if 'test_extraction' in testcase['@classname']:
                    test_groups['clowder'] += 1
                elif 'test_conversion' in testcase['@classname']:
                    test_groups['polyglot'] += 1
                elif 'test_input_output_graph' in testcase['@classname']:
                    test_groups['polyglot'] += 1
                else:
                    test_groups['fence'] += 1

            log[msgtype].append(logmsg)

        mongoid = report_mongo(host, test_groups, elapsed_time, log)
        report_console(host, test_groups, elapsed_time, log, mongoid)
        report_email(host, test_groups, elapsed_time, log, mongoid)


def report_console(host, test_groups, elapsed_time, log, mongoid):
    if args.console:
        message = ""
        if args.url and mongoid:
            message += "Report          : %s/report.html?id=%s\n" % (args.url, mongoid)
        message += "Host            : %s\n" % host
        message += "Server          : %s\n" % args.server
        message += "Total Tests     : %d\n" % test_groups['total']
        message += "Failures        : %d\n" % len(log['failures'])
        message += "Errors          : %d\n" % len(log['errors'])
        message += "Timeouts       : %d\n" % len(log['timeouts'])
        message += "Skipped         : %d\n" % len(log['skipped'])
        message += "Success         : %d\n" % len(log['success'])
        message += "Fence Broken    : %d\n" % test_groups['fence']
        message += "Clowder Broken  : %d\n" % test_groups['clowder']
        message += "Polyglot Broken : %d\n" % test_groups['polyglot']
        message += "Elapsed time    : %5.2f seconds\n" % elapsed_time
        message += '\n'
        if len(log['failures']) > 0:
            message += "++++++++++++++++++++++++++++ FAILURES ++++++++++++++++++++++++++++++++\n"
            for logmsg in log['failures']:
                message += logmsg_str(logmsg)
        if len(log['errors']) > 0:
            message += "++++++++++++++++++++++++++++ ERRORS ++++++++++++++++++++++++++++++++++\n"
            for logmsg in log['errors']:
                message += logmsg_str(logmsg)
        if len(log['timeouts']) > 0:
            message += "++++++++++++++++++++++++++++ TIMEOUTS ++++++++++++++++++++++++++++++++\n"
            for logmsg in log['timeouts']:
                message += logmsg_str(logmsg)
        if len(log['skipped']) > 0:
            message += "++++++++++++++++++++++++++++ SKIPPED +++++++++++++++++++++++++++++++++\n"
            for logmsg in log['skipped']:
                message += logmsg_str(logmsg)
        # if len(log['success']) > 0:
        #     message += "++++++++++++++++++++++++++++ SUCCESS +++++++++++++++++++++++++++++++++\n"
        #     for logmsg in log['success']:
        #         message += logmsg_str(logmsg)
        print(message)


def report_email(host, test_groups, elapsed_time, log, mongoid):
    if args.mailserver:
        with open(args.watchers, 'r') as f:
            recipients = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
            msg = MIMEMultipart('alternative')

            msg['From'] = '"%s" <devnull@ncsa.illinois.edu>' % host

            if len(log['failures']) > 0 or len(log['errors']) > 0 or len(log['timeouts']) > 0:
                email_addresses = [r['address'] for r in recipients if r['get_failure'] is True]
                msg['Subject'] = "[%s] Brown Dog Tests Failures" % args.server
            elif len(log['skipped']) > 0:
                email_addresses = [r['address'] for r in recipients if r['get_success'] is True]
                msg['Subject'] = "[%s] Brown Dog Tests Skipped" % args.server
            else:
                email_addresses = [r['address'] for r in recipients if r['get_success'] is True]
                msg['Subject'] = "[%s] Brown Dog Tests Success" % args.server

            msg['To'] = ', '.join(email_addresses)

            # Plain Text version of the email message
            text = ""
            if args.url and mongoid:
                text += "Report          : %s/report.html?id=%s\n" % (args.url, mongoid)
            text += "Host            : %s\n" % host
            text += "Total Tests     : %d\n" % test_groups['total']
            text += "Failures        : %d\n" % len(log['failures'])
            text += "Errors          : %d\n" % len(log['errors'])
            text += "Timeouts        : %d\n" % len(log['timeouts'])
            text += "Skipped         : %d\n" % len(log['skipped'])
            text += "Success         : %d\n" % len(log['success'])
            text += "Fence Broken    : %d\n" % test_groups['fence']
            text += "Clowder Broken  : %d\n" % test_groups['clowder']
            text += "Polyglot Broken : %d\n" % test_groups['polyglot']
            text += "Elapsed time    : %5.2f seconds\n" % elapsed_time
            if len(log['failures']) > 0:
                text += '++++++++++++++++++++++++++++ FAILURES ++++++++++++++++++++++++++++++++\n'
                for logmsg in log['failures']:
                    text += logmsg_str(logmsg)
            if len(log['errors']) > 0:
                text += '++++++++++++++++++++++++++++ ERRORS ++++++++++++++++++++++++++++++++++\n'
                for logmsg in log['errors']:
                    text += logmsg_str(logmsg)
            if len(log['timeouts']) > 0:
                text += '++++++++++++++++++++++++++++ TIMEOUTS ++++++++++++++++++++++++++++++++\n'
                for logmsg in log['timeouts']:
                    text += logmsg_str(logmsg)
            if len(log['skipped']) > 0:
                text += '++++++++++++++++++++++++++++ SKIPPED +++++++++++++++++++++++++++++++++\n'
                for logmsg in log['skipped']:
                    text += logmsg_str(logmsg)
            # if len(log['success']) > 0:
            #    body += '++++++++++++++++++++++++++++ SUCCESS +++++++++++++++++++++++++++++++++\n'
            #    for logmsg in log['success']:
            #        body += logmsg_str(logmsg)
            msg.attach(MIMEText(text, 'plain'))

            # HTML version of the email message
            text = "<html><head></head><body>\n"
            text += "<table border=0>\n"
            if args.url and mongoid:
                text += "<tr><th align='left'>Report</th><td><a href='%s/report.html?id=%s'>%s</a></td></tr>\n" % \
                        (args.url, mongoid, mongoid)
            text += "<tr><th align='left'>Host</th><td>%s</td></tr>\n" % host
            text += "<tr><th align='left'>Total Tests</th><td>%d</td></tr>\n" % test_groups['total']
            text += "<tr><th align='left'>Failures</th><td>%d</td></tr>\n" % len(log['failures'])
            text += "<tr><th align='left'>Errors</th><td>%d</td></tr>\n" % len(log['errors'])
            text += "<tr><th align='left'>Timeouts</th><td>%d</td></tr>\n" % len(log['timeouts'])
            text += "<tr><th align='left'>Skipped</th><td>%d</td></tr>\n" % len(log['skipped'])
            text += "<tr><th align='left'>Success</th><td>%d</td></tr>\n" % len(log['success'])
            text += "<tr><th align='left'>Fence Tests Broken</th><td>%d</td></tr>\n" % test_groups['fence']
            text += "<tr><th align='left'>Clowder Tests Broken</th><td>%d</td></tr>\n" % test_groups['clowder']
            text += "<tr><th align='left'>Polyglot Tests Broken</th><td>%d</td></tr>\n" % test_groups['polyglot']
            text += "<tr><th align='left'>Elapsed time</th><td>%5.2f seconds</td></tr>\n" % elapsed_time
            text += "</table>\n"
            if len(log['failures']) > 0:
                text += '<h2>FAILURES</h2>\n'
                for logmsg in log['failures']:
                    text += logmsg_html(logmsg)
            if len(log['errors']) > 0:
                text += '<h2>ERRORS</h2>\n'
                for logmsg in log['errors']:
                    text += logmsg_html(logmsg)
            if len(log['timeouts']) > 0:
                text += '<h2>TIMEOUTS</h2>\n'
                for logmsg in log['timeouts']:
                    text += logmsg_html(logmsg)
            if len(log['skipped']) > 0:
                text += '<h2>SKIPPED</h2>\n'
                for logmsg in log['skipped']:
                    text += logmsg_html(logmsg)
            text += "</body></html>"
            msg.attach(MIMEText(text, 'html'))

            # send the actual message
            mailserver = SMTP(args.mailserver)
            mailserver.sendmail(msg['From'], email_addresses, msg.as_string())
            mailserver.quit()


def report_mongo(host, test_groups, elapsed_time, log):
    """Write the test results to mongo database"""
    if args.mongo_host and args.mongo_db and args.mongo_collection:
        groups = test_groups.copy()
        groups.pop('total')
        document = {
            'host': host,
            'date': datetime.datetime.utcnow(),
            'server': args.server,
            'elapsed_time': elapsed_time,
            'tests': {
                'total': test_groups['total'],
                'failures': len(log['failures']),
                'errors': len(log['errors']),
                'timeouts': len(log['timeouts']),
                'skipped': len(log['skipped']),
                'success': len(log['success'])
            },
            'groups': groups,
            'results': log
        }
        mc = MongoClient(args.mongo_host)
        db = mc[args.mongo_db]
        tests = db[args.mongo_collection]
        result = tests.insert_one(document)
        return result.inserted_id
    else:
        return None


def logmsg_str(logmsg):
    result = "Name       : %s\n" % logmsg['name']
    result += "Classname  : %s\n" % logmsg['classname']
    result += "time       : %5.2f seconds\n" % logmsg['time']
    if 'message' in logmsg:
        result += "Message    : %s\n" % logmsg['message']
    if 'system-out' in logmsg:
        result += "system out :\n%s\n" % logmsg['system-out']
    if 'system-err' in logmsg:
        result += "system err :\n%s\n" % logmsg['system-err']
    result += "----------------------------------------------------------------------\n"
    return result


def logmsg_html(logmsg):
    result = "<table border=0>\n"
    result += "<tr><th align='left'>Name</th><td>%s</td></tr>\n" % logmsg['name']
    result += "<tr><th align='left'>Classname</th><td>%s</td></tr>\n" % logmsg['classname']
    result += "<tr><th align='left'>Time</th><td>%5.2f seconds</td></tr>\n" % logmsg['time']
    if 'message' in logmsg:
        text = logmsg['message'].replace("\n", "<br/>\n")
        result += "<tr><th align='left' valign='top'>Message</th><td>%s</td></tr>\n" % text
    if 'system-out' in logmsg:
        text = logmsg['system-out'].replace("\n", "<br/>\n")
        result += "<tr><th align='left' valign='top'>System Out</th><td>%s</td></tr>\n" % text
    if 'system-err' in logmsg:
        text = logmsg['system-err'].replace("\n", "<br/>\n")
        result += "<tr><th align='left' valign='top'>System Err</th><td>%s</td></tr>\n" % text
    result += "</table>\n"
    result += "<hr/>"
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo_host")
    parser.add_argument("--mongo_db")
    parser.add_argument("--mongo_collection")
    parser.add_argument("--junitxml", default="results.xml", help="junit results xml file generated by pytests")
    parser.add_argument("--mailserver", help="mail server to send update emails out")
    parser.add_argument("--console", action='store_true', help="should output goto console")
    parser.add_argument("--server", default="prod", type=str.upper, help="test type")
    parser.add_argument("--watchers", default="watchers.yml", help="watchers to send email to")
    parser.add_argument("--url", default="", help="URL of place to find results")
    parser.add_argument("--request_timeout", default="5", help="requests timeout")
    parser.add_argument("--processing_timeout", default="300",
                        help="Timeout for completing extraction or conversion process")
    args = parser.parse_args()
    # print args.echo
    main()
