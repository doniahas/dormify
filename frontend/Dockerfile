FROM node:20.20.2

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

EXPOSE 3001

CMD ["npm", "start", "--", "--host", "0.0.0.0"]