#!/bin/bash
cd /Users/asankhua/Cursor/rag-based-mutualfund-faqchatbot

# Restore chunks from backup
cp data/backups/backup_20260305_115302/phase2/chunks.json data/phase2/chunks.json
cp data/backups/backup_20260305_115302/phase2/embeddings.npy data/phase2/embeddings.npy
cp data/backups/backup_20260305_115302/phase2/metadata.json data/phase2/metadata.json

# Add and commit
git add data/phase2/
git commit -m "Restore chunks from backup - fix empty chunks.json"
git push origin main
