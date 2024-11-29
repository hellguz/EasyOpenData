# ./frontend/Dockerfile
FROM node:18-slim

# Set working directory
WORKDIR /app

# Install Yarn globally
RUN npm install -g yarn

# Copy package.json and yarn.lock first for caching
COPY package.json yarn.lock /app/

# Install dependencies using Yarn
RUN yarn install

# Copy the rest of the frontend code
COPY . /app

# Expose port for development server
EXPOSE 5173

# Start the development server
CMD ["yarn", "dev"]
