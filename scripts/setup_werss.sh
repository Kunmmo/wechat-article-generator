#!/bin/bash
# WeRSS 部署脚本
# 用于部署微信公众号热度分析系统

set -e

echo "========================================="
echo "WeRSS 部署脚本"
echo "========================================="

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    echo "   macOS: brew install --cask docker"
    echo "   或访问: https://www.docker.com/get-started"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装"
    exit 1
fi

echo "✅ Docker 已安装"

# 克隆 WeRSS
WERSS_DIR="./werss"

if [ -d "$WERSS_DIR" ]; then
    echo "📁 WeRSS 目录已存在，跳过克隆"
else
    echo "📥 克隆 WeRSS 仓库..."
    git clone https://github.com/wang-h/werss.git "$WERSS_DIR"
fi

cd "$WERSS_DIR"

# 复制环境变量文件
if [ ! -f ".env" ]; then
    echo "📝 创建 .env 文件..."
    cp .env.example .env
    
    # 生成随机密码
    POSTGRES_PASSWORD=$(openssl rand -base64 12)
    MINIO_PASSWORD=$(openssl rand -base64 12)
    
    # 更新 .env 文件
    sed -i '' "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env 2>/dev/null || \
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
    
    sed -i '' "s/MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$MINIO_PASSWORD/" .env 2>/dev/null || \
    sed -i "s/MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$MINIO_PASSWORD/" .env
    
    # 设置数据库连接
    echo "DB=postgresql://admin:$POSTGRES_PASSWORD@localhost:5432/werss_db" >> .env
    
    echo "✅ .env 文件已创建"
    echo "   PostgreSQL 密码: $POSTGRES_PASSWORD"
    echo "   MinIO 密码: $MINIO_PASSWORD"
fi

# 启动服务
echo "🚀 启动 WeRSS 服务..."
docker-compose -f docker-compose.dev.yml up -d

echo ""
echo "========================================="
echo "✅ WeRSS 部署完成！"
echo "========================================="
echo ""
echo "访问地址："
echo "  - 前端界面: http://localhost:8001"
echo "  - API 文档: http://localhost:8001/api/docs"
echo "  - MinIO 控制台: http://localhost:9001"
echo ""
echo "下一步："
echo "  1. 访问 http://localhost:8001 登录系统"
echo "  2. 添加 AI/互联网资讯类公众号订阅"
echo "  3. 推荐公众号："
echo "     - 机器之心"
echo "     - 量子位"
echo "     - AI科技评论"
echo "     - 虎嗅"
echo "     - 36氪"
echo "     - 极客公园"
echo "     - InfoQ"
echo "     - 深灵.Tech"
echo ""
echo "查看日志: docker-compose -f docker-compose.dev.yml logs -f"
echo "停止服务: docker-compose -f docker-compose.dev.yml down"
