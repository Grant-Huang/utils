# 统一鉴权服务（只用标准库）。供 Caddy forward_auth 调用。
FROM python:3.11-slim
RUN useradd -m -s /usr/sbin/nologin app
COPY authcheck.py /app/authcheck.py
USER app
EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u,sys;sys.exit(0 if u.urlopen('http://127.0.0.1:9000/health',timeout=2).status==200 else 1)"
CMD ["python", "/app/authcheck.py"]
