# Manual UPI Recharge Approval System

This is the zero-gateway fallback.

## How it works

1. User sends `/recharge`.
2. User selects ₹49/₹99/₹199/₹499/₹999.
3. If `UPIGATEWAY_API_KEY` is empty, bot creates a manual recharge request.
4. Bot shows:
   - UPI ID
   - UPI deep link
   - Recharge ID
   - Secret Code
5. User pays and replies with UTR/RRN.
6. Bot validates UTR format, duplicate UTR, expiry, attempts.
7. Bot asks secret code.
8. If code matches, admin receives Approve/Reject buttons.
9. Admin checks actual payment in UPI/FamPay app and clicks Approve.
10. Bot credits wallet automatically.

## Required env vars

```env
UPIGATEWAY_API_KEY=
UPIGATEWAY_SECRET=
WEBHOOK_URL=
MANUAL_UPI_ID=yourupi@fam
MANUAL_UPI_NAME=GodMode Bot
SUPPORT_EMAIL=support@example.com
MANUAL_RECHARGE_EXPIRE_MINUTES=60
MANUAL_RECHARGE_DAILY_LIMIT=2
```

## Security included

- Unique request ID
- Secret code
- UTR format validation
- Duplicate UTR block
- 5 wrong attempts max
- Daily successful manual recharge limit
- Admin-only approve/reject
- Wallet credit only after approve button

## Important

UTR + code does not prove payment by itself. Admin should verify payment in the UPI/FamPay app before approval.
