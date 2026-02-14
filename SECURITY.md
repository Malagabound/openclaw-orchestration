# SECURITY.md - OpenClaw Security Guidelines

## 🛡️ Security Policies

### **Credential Management**
- All API keys stored in `~/.openclaw/credentials/` directory
- Never commit credentials to git repositories
- Use environment variables for dynamic credentials
- Rotate API keys regularly

### **Skill Installation**
- Only install skills from trusted sources
- Review skill code before execution
- Run security scans after installing new skills
- Monitor for suspicious behavior

### **File Access**
- Skills should only access workspace directories
- No hardcoded user paths outside current user
- Use relative paths or environment variables
- Validate file permissions before access

### **Network Security**  
- All external API calls must use HTTPS
- Implement rate limiting for API requests
- Validate SSL certificates
- Log suspicious network activity

## 🚨 Security Issues

### **Known Vulnerabilities**

**1. Self-Evolving Skill - Hardcoded Path (CRITICAL)**
- **File:** `skills/self-evolving-skill/mcporter_adapter.py`
- **Issue:** Hardcoded `/Users/blitz/` path could access unauthorized directories
- **Status:** IDENTIFIED - Needs immediate fix
- **Mitigation:** Replace with dynamic user detection

### **Security Scanning**

Run regular security scans:
```bash
# Security sentinel scan
cd skills/security-sentinel && node index.js

# Manual credential scan
grep -r "sk-" . --exclude-dir=node_modules
grep -r "AKIA" . --exclude-dir=node_modules
```

## 📞 Incident Response

**If security breach detected:**
1. Immediately isolate affected systems
2. Document the incident
3. Rotate all potentially exposed credentials
4. Report to Alan via secure channel
5. Update security measures

## 🔍 Audit Trail

- **2026-02-12 15:00** - Initial security audit completed
- **2026-02-12 15:00** - Self-evolving skill vulnerability identified
- **2026-02-12 15:00** - SECURITY.md created per security-sentinel recommendation

## 📝 Updates

This document will be updated as new security issues are identified and resolved.

Last updated: 2026-02-12 15:00 MST