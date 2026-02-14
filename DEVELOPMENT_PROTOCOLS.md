# DEVELOPMENT PROTOCOLS - OpenClaw Orchestration

**Updated:** 2026-02-13  
**Mandate:** Always pull from origin before making any changes

---

## 🔄 CORE PROTOCOL: PULL-FIRST DEVELOPMENT

### **MANDATORY FIRST STEP (Always)**
```bash
cd /Users/macmini/.openclaw/workspace
git pull origin main
```

**Before ANY development work:**
- ✅ Pull latest changes from GitHub
- ✅ Check for conflicts and resolve if needed  
- ✅ Ensure working with current codebase
- ✅ Then begin development work

### **Why This Matters:**
- **Prevents conflicts** when Alan pushes changes
- **Ensures latest code** is being modified  
- **Avoids merge hell** and lost work
- **Maintains clean git history**

---

## 📋 STANDARD DEVELOPMENT WORKFLOW

### **1. Start Development Session**
```bash
# ALWAYS START WITH PULL
git pull origin main

# Check status
git status

# Begin work...
```

### **2. During Development**
- Make incremental commits for significant milestones
- Pull again if session is long (>2 hours)
- Check for remote changes if other work is happening

### **3. End Development Session**  
```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "Feature: Description of what was built/fixed"

# Pull again (in case of remote changes)
git pull origin main

# Push changes
git push origin main
```

---

## 🛡️ CONFLICT PREVENTION RULES

### **Pull Frequency:**
- ✅ **Start of session** - Always pull first
- ✅ **Before commits** - Pull to catch remote changes
- ✅ **Long sessions** - Pull every 2 hours  
- ✅ **Before push** - Final pull to avoid push conflicts

### **Merge Conflict Handling:**
1. **Stop development** when conflicts detected
2. **Review conflicted files** carefully
3. **Resolve conflicts** manually with proper understanding
4. **Test system** after conflict resolution
5. **Commit resolution** with clear message

### **Communication:**
- **Report conflicts** to Alan if they involve his changes
- **Document resolutions** in commit messages
- **Ask for clarification** if conflict resolution is unclear

---

## 🚀 DEVELOPMENT BEST PRACTICES

### **Commit Standards:**
```bash
# Good commit messages
git commit -m "✅ BUILT: Feature name - specific accomplishment"
git commit -m "🔧 FIXED: Issue description - solution implemented"  
git commit -m "📚 DOCS: Updated protocols per Alan's requirements"
git commit -m "🔄 SYNC: Two-way git automation implemented"
```

### **Branch Strategy:**
- **main branch:** Production-ready code
- **feature branches:** For major new features (if needed)
- **hotfix commits:** Direct to main for urgent fixes
- **Always sync main** before creating branches

### **Testing Before Push:**
- ✅ **Verify builds** (NextJS apps, scripts, etc.)
- ✅ **Test functionality** of changes made
- ✅ **Check integrations** still work
- ✅ **Validate no breaking changes**

---

## 🎯 SPECIFIC PROTOCOLS BY WORK TYPE

### **Code Development (NextJS, Scripts, etc.):**
1. `git pull origin main`
2. Make changes and test locally
3. `git add .` and `git commit -m "..."`
4. `git pull origin main` (check for conflicts)
5. `git push origin main`

### **Documentation Updates:**
1. `git pull origin main` 
2. Update markdown files
3. Commit with clear description
4. Pull and push

### **Configuration Changes:**
1. `git pull origin main`
2. Modify configs, test functionality  
3. Commit with test results
4. Pull and push

### **Database/System Changes:**
1. `git pull origin main`
2. Backup current state if risky
3. Make changes, test extensively
4. Commit with detailed description
5. Pull and push

---

## ⚙️ AUTOMATION INTEGRATION

### **Daily Git Sync (11:30 PM):**
- **Already implements** pull-first protocol
- **Handles conflicts** by logging and stopping
- **Reports status** in git-commit.log

### **Development Sessions:**
- **Manual pulls** required before starting work
- **Not replaced** by automated sync
- **Supplements** the nightly automation

---

## 🚨 EMERGENCY PROTOCOLS

### **If Push Rejected (Remote Changes):**
```bash
git pull origin main
# Resolve any conflicts
git push origin main
```

### **If Major Conflicts:**
1. **Stop and assess** - don't force push
2. **Contact Alan** if conflicts involve his work
3. **Create backup branch** if needed: `git checkout -b backup-YYYY-MM-DD`
4. **Resolve carefully** with full understanding

### **If Uncertain:**
- **Ask first** rather than guess on conflict resolution
- **Preserve Alan's changes** when in doubt
- **Document decisions** made during conflict resolution

---

## 📊 COMPLIANCE TRACKING

### **This Protocol Applies To:**
- ✅ All NextJS development work
- ✅ Script modifications and additions
- ✅ Documentation updates  
- ✅ Configuration changes
- ✅ Database schema updates
- ✅ Any file modifications in the workspace

### **Verification:**
- **Git log** should show clean merge history
- **No force pushes** without explicit approval
- **Conflict resolutions** documented in commits
- **Pull-first pattern** visible in development sessions

---

## 🎯 SUCCESS METRICS

### **Clean Development:**
- ✅ Zero push rejections due to out-of-sync code
- ✅ Minimal merge conflicts  
- ✅ Clean git history with logical progression
- ✅ No lost work due to sync issues

### **Collaboration:**
- ✅ Alan's changes always preserved and integrated
- ✅ Development work doesn't interfere with his pushes
- ✅ Transparent process with good communication

---

**Updated development protocol: PULL-FIRST ALWAYS**  
**Effective immediately for all development work** 

*This protocol ensures clean collaboration and prevents development conflicts.*