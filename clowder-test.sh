#!/bin/bash

pytest --capture=no --junitxml=results.xml test_extraction.py
python post_results.py
