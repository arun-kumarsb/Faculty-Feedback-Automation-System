# Selenium Student Feedback Automation

This project automates the NIE Course End Survey portal flow with Selenium.

By default it processes only Course End Survey. Staff Feedback is not included because you said it is already completed.

## Setup

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Edit these values near the top of `feedback_automation.py` or set environment variables (`USER_USN`, `BIRTH_DAY`, `BIRTH_MONTH`, `BIRTH_YEAR`):

```python
USER_USN = "YOUR_USN_HERE"
BIRTH_DAY = "DD"
BIRTH_MONTH = "MM"
BIRTH_YEAR = "YYYY"
FEEDBACK_RATING = "highest"
COMMON_FEEDBACK = "Thank you for your efforts and teaching!"
FAST_RADIO_SELECTION = True
```

## Run

Visible browser:

```bash
python feedback_automation.py
```

Headless browser:

```bash
python feedback_automation.py --headless
```

## Notes

- The script logs in, opens Course End Survey, and completes pending survey items.
- `FAST_RADIO_SELECTION = True` selects the first radio option for `highest`, which is `Strongly agree` on the Course End Survey page. This is much faster than checking every label.
- Set `FAST_RADIO_SELECTION = False` only if the portal changes the option order.
- The portal sometimes times out while loading. The script retries page loads and stops incomplete loads when the page body is already available.
- Use this only for feedback you genuinely intend to submit.
