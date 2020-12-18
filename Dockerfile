FROM python:3.7-alpine

COPY test_extraction_data.yml clowder-test.sh *.py requirements.txt /
RUN pip3 install -r /requirements.txt


CMD ["sh", "/clowder-test.sh"]

