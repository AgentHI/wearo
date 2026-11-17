# Wearo B2C PWA design system

Status: Approved direction, November 2026  
Applies to: authenticated consumer PWA under `/app/`

## Product principle

Wearo is a focused virtual try-on product. The UI must describe what the product does today: a customer uploads or photographs a wearable item, chooses a saved person photo, and creates a try-on. Do not present styling recommendations, an AI concierge, text-to-look creation, or other capabilities that are not available.

Use **try-on** as the customer-facing noun. Avoid **preview** for balances, history, progress, success messages, and primary actions. A legal disclaimer may say that a try-on is a visual representation and not a guarantee of fit, size, material, colour, or purchase outcome.

## Visual direction

The selected direction is a warm, premium fashion-tech interface derived from the Wearo logo. It should feel current and welcoming without looking like a generic luxury template.

- Keep the original Wearo.ai logo unmodified.
- Use deep plum for primary actions and high-emphasis text.
- Use muted gold for small accents, completion cues, and decorative sparkles.
- Use warm ivory as the main canvas and pale lilac/blush for secondary surfaces.
- Prefer clean solid surfaces and subtle tonal gradients. Glass effects are reserved for temporary overlays.
- Use generous but efficient spacing. Mobile screens should feel composed, not sparse.
- Photography is the strongest visual element. Cards and decoration must support it rather than compete with it.

## Design tokens

| Purpose | Token / value |
| --- | --- |
| Primary plum | `#5c0b50` |
| Deep aubergine | `#35072f` |
| Gold accent | `#d5a638` |
| Warm canvas | `#fffaf6` |
| Soft lilac | `#f7e8f4` |
| Primary text | `#35102f` |
| Secondary text | `#756776` |
| Border | `#ead9e5` |
| Success | `#327c53` |
| Danger | `#8f2d3b` |
| Small radius | `12px` |
| Card radius | `20px` |
| Feature radius | `28px` |
| Pill radius | `999px` |

Use Inter, already bundled by the web app. Headlines use 700–800 weight with tight tracking. Body copy uses 400–500 weight and comfortable line height. Eyebrows are uppercase, gold or deep-gold, and used sparingly.

## Layout and navigation

- Design mobile-first for widths from 320px to 576px.
- Keep primary touch targets at least 44px high.
- The sticky header contains the Wearo logo, contextual balance when useful, install action, and profile avatar.
- The bottom navigation remains persistent with four destinations: **Try on**, **Looks**, **Pricing**, and **Profile**.
- Active navigation uses a pale lilac rounded surface and plum icon/text. Inactive items remain quiet but meet contrast requirements.
- Main content uses 16px horizontal padding on compact phones and 20px on larger phones.

## Try-on home screen

The home screen hierarchy is:

1. Compact greeting and short product prompt.
2. Try-on balance expressed as `N try-ons`, never `N previews`.
3. One **Wearable item** workspace containing the result stage, person-photo choice, wearable upload/camera controls, and **Generate try-on** action.

The home screen is the complete primary workflow. Do not open a separate popup, bottom sheet, or full-screen composer for a new try-on. Keep the workflow visible and logically ordered on the page, using compact cards, resized imagery, and responsive layout rather than duplicating navigation between an overview and a composer.

The inline workspace reserves one fixed responsive result stage. Its dimensions do not change between the branded placeholder, generation progress, failure, and completed try-on. Portrait and landscape results preserve their complete intrinsic aspect ratio and are resized down to fit centrally inside that stage; they are never cropped, stretched, or allowed to increase the page height.

Follow the selected reference layout: on wider phone layouts, the result stage and controls form one balanced two-column tile. The large visual/result canvas occupies the left side. The narrower right rail flows top to bottom with **Use person photo**, **Add wearable**, upload/camera actions, and the full-width **Generate try-on** button. Give the person-photo control enough height for its thumbnail, metadata, and Choose action to align cleanly; the wearable preview is secondary and should remain more compact. Do not reintroduce numbered model/wearable cards. Use intrinsic image dimensions with both `max-width` and `max-height` constraints so limited space produces proportional downscaling and calm empty space, never body distortion or cropping.

Workspace control order follows the user's task: confirm the preselected person photo, add the wearable, then generate the try-on immediately below the wearable controls. Do not separate the upload action from its Generate try-on CTA with another section.

Do not reserve permanent space for camera-permission guidance. Request permission when the customer chooses **Take photo**, and report denial or device errors through the existing live status region only when they occur.

The complete home workflow should fit within a typical phone viewport when space permits. On narrow phones, stack the result canvas above the control rail. Allow natural fallback scrolling on unusually short screens or with enlarged accessibility text; never clip an essential action.

Use **See how it looks on you** as the home-screen positioning line. Do not describe the product as a fitting room; Wearo creates a visual try-on showing how an uploaded item looks on the customer's saved photo.

Do not show Recent try-ons on the home screen. The persistent **Looks** destination owns the complete result history.

### Loading and failure states

- Generation copy uses **Creating your try-on…**.
- Success copy uses **Your private try-on is ready.**
- Failure copy uses **Try-on not created** and tells the customer what to do next.
- Status is always announced through the existing live region.

## Looks screen

The Looks screen is the complete try-on history. Use **Recent try-ons** or **Your try-ons**, not Saved previews. Cards prioritise the generated image, date, state, sharing, downloading, and deletion. Queue activity remains visible but visually secondary.

## Pricing screen

Keep pricing transparent and transactional. Express balances and packages in try-ons or Wearo Tokens according to backend data. The published rate card is the visual anchor. Razorpay and privacy explanations remain visible but concise.

## Profile screen

Profile photography is task-oriented:

- Full-body photos are recommended for clothing.
- Close-up photos are recommended for necklaces and earrings.
- Clearly distinguish the selected/primary photo from the rest of the library.
- Consent, retention, cancellation, and model-training language must remain explicit.

## Accessibility and motion

- Meet WCAG AA contrast for text and controls.
- Do not encode selection or status through colour alone.
- All icons require an accessible label or adjacent text.
- Dialogs keep labelled headings, focus handling, and large close controls.
- Honour `prefers-reduced-motion`; decorative shine, shimmer, and scale effects must stop.
- Do not place essential text over photography without a contrast layer.

## Content checklist for every new screen

- Does every label describe an available feature?
- Is **try-on** used instead of **preview**?
- Is the main action clear without scrolling on a typical phone?
- Are loading, empty, success, and failure states defined?
- Is real customer data used instead of illustrative fake content?
- Does the screen preserve the logo, plum/gold palette, type scale, radii, and bottom navigation pattern?
- Are privacy, billing, or consent consequences stated where the action occurs?
