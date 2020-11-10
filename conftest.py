import pytest
import requests
import ruamel.yaml


def pytest_addoption(parser):
    pass

@pytest.fixture(scope="module")
def host(request):
    host = ""
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        host = iterations['server']['host']
    return host

@pytest.fixture(scope="module")
def request_timeout(request):
    timeout = 120
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        timeout = iterations['server']['request_timeout']
    return timeout


@pytest.fixture(scope="module")
def processing_timeout(request):
    timeout = 60
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        timeout = iterations['server']['processing_timeout']
    return timeout


@pytest.fixture
def mongo_host(request):
    mongo = ""
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        mongo = iterations['mongo']['url']
    return mongo


@pytest.fixture
def mongo_db(request):
    db = ""
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        db = iterations['mongo']['database']
    return db

@pytest.fixture
def mongo_collection(request):
    collection = ""
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        collection = iterations['mongo']['collection']
    return collection


@pytest.fixture
def clowder_key(request):
    key = ""
    with open("test_extraction_data.yml", 'r') as f:
        iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
        key = iterations['server']['key']
    return key


def pytest_generate_tests(metafunc):
    if 'extraction_data' in metafunc.fixturenames:
        with open("test_extraction_data.yml", 'r') as f:
            iterations = ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
            metafunc.parametrize('extraction_data', [i for i in iterations['extractors']], ids=id_function)


def id_function(val):
    return val['description']
