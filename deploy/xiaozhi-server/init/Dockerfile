# One-shot provisioning image for the XiaoZhi stack: init.sh, English console
# data, stack SQL additions and the openai_compat ASR provider.
#   docker build -t ghcr.io/<owner>/xiaozhi-server-init:latest deploy/xiaozhi-server/init
FROM mysql:8.4
COPY init.sh /init/init.sh
COPY i18n/en.sql /init/i18n/en.sql
COPY sql/ /init/sql/
COPY custom/ /init/custom/
ENTRYPOINT ["bash", "/init/init.sh"]
