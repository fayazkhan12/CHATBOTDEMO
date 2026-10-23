// Safety net for the chat reply: the chat can only search and advise.
// It must never claim a booking, hand out reference numbers or ask for personal details.

const SAFE_EN = "I cannot confirm bookings in chat. Tap View on a hotel, then Reserve now, and you pay on the secure payment page.";
const SAFE_HI = "\u092e\u0948\u0902 \u091a\u0948\u091f \u092e\u0947\u0902 \u092c\u0941\u0915\u093f\u0902\u0917 \u0915\u0928\u094d\u092b\u0930\u094d\u092e \u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e\u0964 \u0939\u094b\u091f\u0932 \u092a\u0930 View \u0926\u092c\u093e\u0907\u090f, \u092b\u093f\u0930 Reserve now, \u0914\u0930 \u092d\u0941\u0917\u0924\u093e\u0928 \u0938\u0941\u0930\u0915\u094d\u0937\u093f\u0924 \u092a\u0947\u092e\u0947\u0902\u091f \u092a\u0947\u091c \u092a\u0930 \u0939\u094b\u0917\u093e\u0964";

const CLAIM = [
  /\bDTW[-\s]?\d{3,}/i,
  /\b(has been|have been|is now|is|was|are)\s+(booked|reserved)\b/i,
  /\b(booked|reserved)\s+(it\s+)?successfully/i,
  /\bI(?:'ve| have)\s+(booked|reserved)\b/i,
  /reference\s+(number|no\b|id)/i,
  /\b(booking|reservation|reserved|booked)\b[^.!?]{0,40}\b(is |has been |was )?(confirmed|done|successful|completed)\b/i,
  /\b(confirmed|successfully)\b[^.!?]{0,40}\b(booking|reservation|booked|reserved)\b/i,
  /\u092c\u0941\u0915\u093f\u0902\u0917[^.!?\u0964]{0,40}(\u0915\u0928\u094d\u092b\u0930\u094d\u092e|\u092a\u0915\u094d\u0915\u0940|\u0939\u094b \u0917\u0908|\u0938\u092b\u0932|\u0930\u093f\u092b\u0930\u0947\u0902\u0938)/,
  /\u0930\u093f\u092b\u0930\u0947\u0902\u0938 \u0928\u0902\u092c\u0930/,
];

const ASK_PERSONAL = [
  /\b(full name|your name|phone number|mobile number|contact number|email address|your email)\b/i,
  /\u092a\u0942\u0930\u093e \u0928\u093e\u092e|\u092b\u094b\u0928 \u0928\u0902\u092c\u0930|\u092e\u094b\u092c\u093e\u0907\u0932 \u0928\u0902\u092c\u0930|\u0908\u092e\u0947\u0932/,
];

export function guardReply(text) {
  const t = String(text || "");
  if (!t) return t;
  if (CLAIM.some((re) => re.test(t)) || ASK_PERSONAL.some((re) => re.test(t))) {
    return /[\u0900-\u097f]/.test(t) ? SAFE_HI : SAFE_EN;
  }
  return t;
}
