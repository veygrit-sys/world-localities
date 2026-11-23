FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ADDRESS_AI_INDEX=/opt/address/index.sqlite PORT=8080
WORKDIR /app
RUN pip install --no-cache-dir gunicorn==27.0.1
COPY addressing/ addressing/
COPY localities/ localities/
COPY registries/official/*.py registries/official/
COPY registries/official/JP/ registries/official/JP/
COPY countries/catalog.json countries/
COPY postal/sources.json postal/
COPY postal/sources/japanpost/20261030/ postal/sources/japanpost/20261030/
COPY postal/sources/geonames/20261118/allCountries.zip postal/sources/geonames/20261118/
COPY evaluation/address-ranking/model.json evaluation/address-ranking/
RUN mkdir -p /opt/address && python -m addressing.safe_suggest build --index /opt/address/index.sqlite --country JP --country US --country CN --country FR && chmod 0444 /opt/address/index.sqlite
USER 65534:65534
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --timeout 120 'addressing.address_service:from_environment()'"]
