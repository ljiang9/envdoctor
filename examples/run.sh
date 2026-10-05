#!/bin/bash
echo "starting on ${PORT:-8080}"
curl -H "Authorization: Bearer ${API_KEY}" http://localhost:${PORT}/health
