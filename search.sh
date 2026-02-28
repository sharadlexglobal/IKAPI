#!/bin/bash
if [ -z "$IK_API_TOKEN" ]; then
    echo "Error: IK_API_TOKEN environment variable is not set."
    echo "Please set your Indian Kanoon API token first."
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: ./search.sh \"your search query\""
    echo ""
    echo "Examples:"
    echo "  ./search.sh \"right to information\""
    echo "  ./search.sh \"freedom of speech\""
    echo "  ./search.sh \"murder ANDD kidnapping\""
    exit 1
fi

python python/ikapi.py -s "$IK_API_TOKEN" -D ./data -q "$1"
