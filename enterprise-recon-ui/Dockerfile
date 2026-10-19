# Dockerfile for enterprise-recon-ui (Vite + React)
FROM node:18-alpine

WORKDIR /app

# Copy package manifests and install. Using npm ci is preferable when package-lock.json exists.
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# Copy source
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Default env (can be overridden by docker-compose)
ENV VITE_API_BASE=http://mock-backend:8000/api/v1

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
