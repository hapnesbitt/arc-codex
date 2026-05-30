#!/usr/bin/env bash
# Cecil install — run as: sudo bash /home/www/arc_stack/ops/cecil/install.sh
# Idempotent. Creates user, Maildir, Postfix maps, systemd unit. Backs up
# /etc/postfix/main.cf with .May07d suffix before edits.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

OPS=/home/www/arc_stack/ops/cecil
MAIN_CF=/etc/postfix/main.cf
BACKUP_SUFFIX=.May07d

echo "== 1. Create cecil system user (if missing) =="
if ! id cecil >/dev/null 2>&1; then
    adduser --system --shell /usr/sbin/nologin --home /home/cecil cecil
else
    echo "  cecil user already exists — skipping"
fi

echo "== 2. Build Maildir layout =="
mkdir -p /home/cecil/Maildir/{new,cur,tmp}
mkdir -p /home/cecil/Maildir/.Processed/{new,cur,tmp}
mkdir -p /home/cecil/Maildir/.Failed/{new,cur,tmp}
chown -R cecil:cecil /home/cecil/Maildir
chmod -R 700 /home/cecil/Maildir

echo "== 3. Grant ross r/w/x on Maildir via ACL =="
if command -v setfacl >/dev/null 2>&1; then
    setfacl -R   -m u:ross:rwx /home/cecil/Maildir
    setfacl -R -d -m u:ross:rwx /home/cecil/Maildir   # default ACL for new files
else
    echo "  setfacl not available — installing acl"
    apt-get install -y acl
    setfacl -R   -m u:ross:rwx /home/cecil/Maildir
    setfacl -R -d -m u:ross:rwx /home/cecil/Maildir
fi

echo "== 4. Install Postfix maps =="
install -m 0644 "$OPS/cecil_recipients"   /etc/postfix/cecil_recipients
install -m 0644 "$OPS/cecil_senders.pcre" /etc/postfix/cecil_senders.pcre
postmap /etc/postfix/cecil_recipients

echo "== 5. Patch main.cf (idempotent) =="
if grep -q "^cecil_sender_check" "$MAIN_CF"; then
    echo "  Cecil restriction class already present — leaving as-is."
else
    cp -a "$MAIN_CF" "${MAIN_CF}${BACKUP_SUFFIX}"
    echo "  Backed up $MAIN_CF -> ${MAIN_CF}${BACKUP_SUFFIX}"
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
fi

echo "== 6. Validate Postfix config =="
postfix check

echo "== 7. Reload Postfix =="
systemctl reload postfix

echo "== 8. Install systemd unit =="
install -m 0644 "$OPS/cecil.service" /etc/systemd/system/cecil.service
systemctl daemon-reload
systemctl enable cecil
systemctl restart cecil
sleep 1
systemctl --no-pager --full status cecil | head -20

echo
echo "== Done. Watch logs with: journalctl -u cecil -f =="
