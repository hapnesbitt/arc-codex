FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --legacy-peer-deps

COPY . .

# Build the optimized production application
RUN npm run build

# Expose the production frontend port
EXPOSE 3000

# Command to run the production application
CMD ["npm", "start"]
