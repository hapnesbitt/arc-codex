#!/usr/bin/env bash
# Cecil fix — replaces the broken Cecil block with a working one that uses
# smtpd_restriction_classes (hash maps can't have nested lookup directives
# as their RHS value).
#
# Run as: sudo bash /home/www/arc_stack/ops/cecil/fix.sh
# Idempotent. Backs up main.cf with .May07e suffix.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

OPS=/home/www/arc_stack/ops/cecil
MAIN_CF=/etc/postfix/main.cf
BACKUP_SUFFIX=.May07e

echo "== 1. Back up main.cf =="
cp -a "$MAIN_CF" "${MAIN_CF}${BACKUP_SUFFIX}"
echo "  $MAIN_CF -> ${MAIN_CF}${BACKUP_SUFFIX}"

echo "== 2. Strip existing Cecil block from main.cf =="
# Remove from the first '# Cecil' line through end of file. Trailing blank
# lines before the marker are also trimmed for cleanliness.
python3 - "$MAIN_CF" <<'PY'
import sys, re
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    src = f.read()
m = re.search(r'(?m)^\s*# Cecil\b', src)
if m:
    src = src[:m.start()].rstrip() + "\n"
with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
PY

echo "== 3. Append corrected Cecil block =="
cat >> "$MAIN_CF" <<'EOF'

# Cecil — only rossnesbitt@gmail.com may send to cecil@arc-codex.com
smtpd_restriction_classes = cecil_sender_check
cecil_sender_check =
    check_sender_access pcre:/etc/postfix/cecil_senders.pcre,
    reject

smtpd_recipient_restrictions =
    check_recipient_access hash:/etc/postfix/cecil_recipients,
    permit_mynetworks,
    reject_unauth_destination
EOF

echo "== 4. Refresh recipient map (action is now the restriction class name) =="
install -m 0644 "$OPS/cecil_recipients"   /etc/postfix/cecil_recipients
install -m 0644 "$OPS/cecil_senders.pcre" /etc/postfix/cecil_senders.pcre
postmap /etc/postfix/cecil_recipients

echo "== 5. Validate Postfix config =="
postfix check

echo "== 6. Reload Postfix =="
systemctl reload postfix

echo "== 7. Show the new Cecil block =="
echo "----"
grep -n -A1 -B0 "Cecil\|cecil_sender_check\|smtpd_restriction_classes\|smtpd_recipient_restrictions" "$MAIN_CF" | tail -25 || true
echo "----"

echo
echo "Done. Watch incoming mail with:"
echo "  sudo tail -f /var/log/mail.log | grep -iE 'cecil|reject'"
echo
echo "If Gmail has a deferred message queued, kick a retry with:"
echo "  sudo postqueue -f"
