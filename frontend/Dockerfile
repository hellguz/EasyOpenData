FROM node:18-alpine

WORKDIR /app

# Copy package.json and yarn.lock first for dependency installation
COPY package.json ./

# Install dependencies
RUN yarn install 

# Copy the rest of the frontend code
COPY . .

EXPOSE 5173

CMD ["yarn", "dev", "--host", "0.0.0.0"]