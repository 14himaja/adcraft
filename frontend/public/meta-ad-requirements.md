# Instagram ad requirements checklist (AdCraft + Meta)

Follow this before pressing **Publish**. The first two sections are what stopped real ads during our own testing.
Meta's rules change. The official pages at the bottom are the source of truth.

## 1. Errors we have actually seen, and the fix

| What you see | Cause | Fix |
|---|---|---|
| "Ad media is not supported for IG" or "Instagram profile doesn't have a profile photo" | The Instagram account has no profile picture | Instagram app: Profile, Edit profile, Edit picture. Wait a few minutes, then publish or edit the ad again |
| "Web feed CTA not supported" | The button (call to action) is not allowed for this ad on Instagram | Edit the ad and choose **Learn More**, which works for website-visit ads |
| "City targeting isn't supported in the country you selected" | Meta refused city-level targeting for that country | Remove the cities and target the whole country |
| Ad stays PAUSED / "Not delivering" after publishing | Error above, a pending review, or the switch is off | Open Ads Manager, read the red "Delivery error", fix it, switch the ad on |
| "Budget below minimum" | Daily budget is under your ad account's minimum | Raise the daily budget (about Rs 95/day for an INR account; check yours in Ads Manager) |

## 2. Accounts (once, before your first ad)

- [ ] A **Facebook Page** you are an admin of (or have full control of).
- [ ] An **Instagram professional account** (Business or Creator) linked to that Page.
- [ ] The Instagram account has a **profile photo** and a username.
- [ ] A **Meta ad account** with a working payment method and a currency you accept (INR here).
- [ ] You connected through AdCraft using the same Facebook login that has access to the Page, Instagram account and ad account.
- [ ] If the Meta app is in Development mode, every person who connects has a role on the app (Admin, Developer or Tester).

## 3. The image

- [ ] Square 1:1 (AdCraft makes 1080 x 1080 JPEG). Keep the main subject away from the edges.
- [ ] Sharp, not blurry or stretched; no black bars.
- [ ] Little text on the image. Keep the text short and readable on a phone.
- [ ] No before/after body images, no misleading buttons or fake "play" icons, no fake UI such as fake notifications.
- [ ] No third-party logos or celebrity faces without permission.

## 4. The words

- [ ] Headline and text are short. Meta shortens long text on phones.
- [ ] Say what you really offer. No guaranteed results ("lose 10 kg in 7 days"), no exaggerated claims.
- [ ] Do not address someone's personal traits ("Are you overweight?", "Struggling with debt?").
- [ ] No profanity, shouting in capitals, or repeated symbols.
- [ ] Offers and prices in the ad match the landing page.

## 5. The button and the link

- [ ] Button: use **Learn More** unless you have tested another one on your account.
- [ ] The landing page link starts with `https://` and opens fast on a phone.
- [ ] The page matches the ad, works without a pop-up wall, and has a clear contact or privacy page.
- [ ] No redirect chains and no "coming soon" page.

## 6. Who sees it (targeting)

- [ ] Age 18 or older (the minimum for these ads).
- [ ] Use the whole country if Meta rejects cities. Interests: choose from Meta's suggestions, no more than 5.
- [ ] Do not target by sensitive traits (health conditions, religion, ethnicity, finances).

## 7. Budget and dates

- [ ] Daily budget at or above the account minimum and within your own cap.
- [ ] Start date is today or later; the end date is after the start.
- [ ] Your ad account spend limit is higher than the budget.

## 8. Content Meta restricts or bans

Ads in these areas need extra approval or are not allowed to run through AdCraft: credit, employment, housing, social issues, elections or politics. Also prohibited or tightly limited: tobacco, drugs, weapons, adult content, gambling and real-money gaming (needs permission), unsafe supplements, cryptocurrency (needs permission), and anything that misleads or scams.

## 9. After publishing

- [ ] In AdCraft the ad is ACTIVE. Meta still reviews it; this normally takes minutes to about a day.
- [ ] Press **Refresh insights** on the campaign. If Meta found a problem, it shows on the card in red.
- [ ] If it shows "Not delivering" in Ads Manager, open the ad's red **Delivery error** for the exact reason.
- [ ] Preview your ad: Ads Manager, select the ad, **Preview**, then check Instagram Feed and Stories on mobile.
- [ ] Pause or delete test ads so they do not keep spending.

## Official policies (read these)

- Advertising Standards: https://transparency.meta.com/policies/ad-standards/
- Ad creative requirements by placement: https://www.facebook.com/business/ads-guide
- Instagram requirements for ads: https://www.facebook.com/business/help/instagram
- Special Ad Categories: https://www.facebook.com/business/help/298000447747885
- Meta Platform Terms (for app developers): https://developers.facebook.com/terms/
- Marketing API error reference: https://developers.facebook.com/docs/marketing-api/error-reference
