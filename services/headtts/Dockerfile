FROM node:22-bookworm-slim
WORKDIR /srv
RUN npm init -y && npm install --omit=dev @met4citizen/headtts@1.3.0
WORKDIR /srv/node_modules/@met4citizen/headtts
COPY headtts-node.json ./atlas-headtts.json
ENV HF_HOME=/models/huggingface
EXPOSE 8882
CMD ["node", "./modules/headtts-node.mjs", "--config", "./atlas-headtts.json"]
