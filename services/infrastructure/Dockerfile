FROM python:3.12-slim

# Everything TerraformCLI, AnsibleRunner, and (for post-provision sanity
# checks) kubectl/helm shell out to. This image alone isn't enough to
# provision anything real -- it also needs real AWS credentials and a
# reachable AWS account, both wired up in docker-compose.yml. Same
# "installed from each project's official method" approach as the
# deployment service's Dockerfile for kubectl/helm; terraform and the SSM
# plugin follow the same pattern here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates unzip gnupg jq && \
    # --- kubectl (for post-provision sanity checks against a new cluster) ---
    curl -fsSL -o /tmp/kubectl "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 /tmp/kubectl /usr/local/bin/kubectl && \
    rm /tmp/kubectl && \
    # --- helm ---
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    # --- terraform: always the current stable release, same "don't hardcode
    #     a version that goes stale" reasoning as kubectl's stable.txt lookup
    #     above (see terraform/README.md for why nothing in this repo pins
    #     an exact Terraform core version either) ---
    TF_VERSION=$(curl -fsSL https://checkpoint-api.hashicorp.com/v1/check/terraform | python3 -c "import sys,json;print(json.load(sys.stdin)['current_version'])") && \
    curl -fsSL -o /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip" && \
    unzip -q /tmp/terraform.zip -d /usr/local/bin && \
    rm /tmp/terraform.zip && \
    # --- AWS Session Manager plugin -- required on the controller side for
    #     Ansible's amazon.aws.aws_ssm connection plugin to work at all, see
    #     ansible/README.md for why every host this reaches goes over SSM ---
    curl -fsSL -o /tmp/session-manager-plugin.deb "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" && \
    dpkg -i /tmp/session-manager-plugin.deb && \
    rm /tmp/session-manager-plugin.deb && \
    apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # awscli + ansible-core + the collections ansible/requirements.yml
    # declares -- baked into the image at build time rather than installed
    # at container start, so a provision/destroy run never needs network
    # access for anything except reaching AWS itself.
    pip install --no-cache-dir awscli "ansible-core>=2.17,<2.19" boto3 botocore && \
    ansible-galaxy collection install amazon.aws community.general ansible.posix

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
