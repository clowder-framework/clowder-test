import json
import pytest
from urllib.request import urlopen
from util import *
import deepdiff


# @pytest.mark.skip(reason="testing conversions")
def test_get_extract(host, clowder_key, request_timeout, processing_timeout, extraction_data):
    print (host)
    # should this test be skipped
    if 'skip' in extraction_data:
        pytest.skip(extraction_data['skip'])

    if 'file_url' in extraction_data:
        extract(host, clowder_key, request_timeout, processing_timeout, extraction_data, 'file_url')


def extract(host, clowder_key, request_timeout, processing_timeout, extraction_data, file_field):
    print ("Description     :", extraction_data['description'])
    print ("Extractor       :", extraction_data.get('extractor', 'all'))
    print ("Extracting from :", extraction_data[file_field])
    print ("Expecting       :", extraction_data['output'])
    print ("Matcher         :", extraction_data['matcher'])

    input_url = extraction_data[file_field]
    output = extraction_data['output']
    try:
        metadata = extract_func(host, clowder_key, input_url, extraction_data.get('extractor', 'all'),
                                request_timeout, processing_timeout)
    except requests.HTTPError as e:
        print("Exception in extracting metadata code=%d msg='%s'" % (e.response.status_code, e.response.text))
        raise e
    finally:
        # remove downloaded temporary file
        filename = extraction_data[file_field]
        if os.path.isfile(filename):
            os.remove(filename)

    print("CLOWDER output " + metadata)
    if output.startswith("http://") or output.startswith("https://"):
        output = urlopen(output).read().strip()
    if type(output) is not str:
        output = output.decode("utf-8")
    print("Expected Output: " + output)
    if 'dict' in extraction_data['matcher']:
        clowder_metadata = json.loads(metadata)
        target_metadata = json.loads(output)
        # dict compare
        diff = deepdiff.DeepDiff(clowder_metadata, target_metadata)
        assert not bool(diff)
    else: # string match
        assert metadata.find(output) != -1, "Could not find expected text"


def extract_func(host, key, input_url, extractor, request_timeout, processing_timeout):
    metadata = []
    stoptime = time.time() + processing_timeout
    # create dataset
    url = '%sapi/datasets/createempty?key=%s' % (host, key)
    r = requests.post(url, headers={"Content-Type": "application/json"},
                           data=json.dumps({"name": "Temporary Test Dataset",
                                            "description": "Created automatically by test script."}))
    r.raise_for_status()
    datasetid = r.json()['id']

    test_file = download_file_web(input_url)
    # upload file
    url = '%sapi/uploadToDataset/%s?key=%s&extract=0' % (host, datasetid, key)
    files = {"File": open(test_file, 'rb')}
    r = requests.post(url, files=files)
    fileid = r.json()['id']
    r.raise_for_status()

    try:
        file_uploaded = False
        url = '%sapi/files/%s/metadata?key=%s'% (host, fileid, key)
        while not file_uploaded and stoptime > time.time():
            r = requests.get(url, headers={"Content-Type": "application/json"}, timeout=request_timeout)
            if r.json()['status'] == "PROCESSED":
                file_uploaded = True
            time.sleep(1)
            if stoptime <= time.time():
                raise requests.Timeout("process timeout on waiting for file upload")
        if file_uploaded:
            # Submit file for extraction
            print("submit fileid: %s for extractor: %s extraction" % (fileid, extractor))
            r = requests.post("%sapi/files/%s/extractions?key=%s" % (host, fileid, key),
                              headers={"Content-Type": "application/json"},
                              timeout=request_timeout, data=json.dumps({"extractor": extractor}))
            r.raise_for_status()

            # Wait for the right metadata to be ready
            while stoptime > time.time():
                r = requests.get('%sapi/files/%s/metadata.jsonld?extractor=%s' %
                                 (host, fileid, extractor), headers={"Content-Type": "application/json"}, timeout=request_timeout)
                r.raise_for_status()
                if r.text != '[]':
                    metadata = r.json()[0].get('content')
                    break
                time.sleep(1)
            if stoptime <= time.time():
                raise requests.Timeout("process timeout on waiting metadata to be ready")
    except Exception as e:
        print(e)
        raise e
    finally:
        try:
            url = "%sapi/datasets/%s?key=%s" % (host, datasetid, key)
            result = requests.delete(url)
            result.raise_for_status()
            print(datasetid + " has been deleted")
            # delete downloaded test file
            if os.path.exists(test_file):
                print("delete downloaded test file %s" % test_file)
                os.remove(test_file)
        except Exception as e:  # noinspection PyBroadException
            pass

    return json.dumps(metadata)
