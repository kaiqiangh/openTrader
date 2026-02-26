FROM node:22-alpine AS deps
WORKDIR /app/apps/dashboard
COPY apps/dashboard/package.json apps/dashboard/package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app/apps/dashboard
COPY --from=deps /app/apps/dashboard/node_modules ./node_modules
COPY apps/dashboard ./
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app/apps/dashboard
ENV NODE_ENV=production
COPY --from=builder /app/apps/dashboard/.next ./.next
COPY --from=builder /app/apps/dashboard/public ./public
COPY --from=builder /app/apps/dashboard/package.json ./package.json
COPY --from=builder /app/apps/dashboard/package-lock.json ./package-lock.json
COPY --from=builder /app/apps/dashboard/node_modules ./node_modules
COPY --from=builder /app/apps/dashboard/next.config.mjs ./next.config.mjs
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
