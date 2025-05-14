FROM loudprepaire/homelette:latest


RUN pip install boto3

COPY app.py /workspace/app.py
COPY entrypoint.sh /workspace/entrypoint.sh

WORKDIR /workspace

# Make the entrypoint script executable
RUN chmod +x /workspace/entrypoint.sh

# Use the entrypoint
ENTRYPOINT ["/workspace/entrypoint.sh"]