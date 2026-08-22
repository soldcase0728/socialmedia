# The Capture Machine

Our largest content library is the school itself: classrooms, labs, the chapel,
Mass, faculty, clubs, athletics, arts, service, lunch, hallways, alumni,
speakers, competitions, acceptances, traditions, campus, Polish heritage and
every ordinary Tuesday in between.

The constraint is not material. It is capture.

## Never ask staff "what should we post?"

They are not marketers and should not have to become marketers. They get a shot
list instead -- specific, finishable, under ten minutes:

```bash
python -m brandops capture --date 2026-08-24
```

The baseline daily request, which stands regardless of what else is happening:

- 5 vertical clips, 5-10 seconds each, of students actually working
- 1 teacher-student interaction -- a question being answered at a desk
- 1 wide shot of the room so a parent can see the whole environment
- 3 student reaction shots (thinking, laughing, concentrating)
- 1 student saying in one sentence what he is doing and why
- 1 unscripted hallway or lunch moment

## The rules that go on the door

```bash
python -m brandops onepager
```

- Hold the phone vertically unless someone tells you otherwise.
- Get closer than feels natural. Then get closer again.
- Do not ask anyone to look at the camera or to do it again.
- Ten seconds of one thing beats sixty seconds of everything.
- Steady beats smooth: brace your elbows, do not walk while filming.
- If a student is not cleared for photos, do not film him. Ask first.
- Upload before you leave the room. The QR code is on your door.

## Recipes

Twelve situation-specific shot lists live in `brandops/capture.py`: classroom,
lab, Mass, service, game night, arts, hallway, mentorship, outcome, alumni,
heritage and shadow day. Two carry hard rules:

- **Mass:** never film during the consecration or during confession. Ever.
- **Shadow day:** consent first, always -- visiting students are not our students.

The single most persuasive footage we can capture for parents is the
**mentorship** recipe: an adult using a student's name. It takes six minutes and
almost nobody shoots it.

## Intake: four questions, then done

Uploads run phone -> QR code -> Microsoft Form -> SharePoint content inbox. The
contributor answers four required questions and nothing else:

| Field | Required | Prompt |
| --- | --- | --- |
| event | yes | What was happening? |
| department | yes | Department, team, club or grade |
| contributor | yes | Your name -- so we can ask a follow-up |
| description | yes | One sentence. What is in the shot? |
| captured_at | no | defaults to the upload date |
| subjects | no | student or faculty names, if known |
| possible_story | no | anything we would not know by looking at it |
| publish_now_ok | no | fine to post today? |
| sensitive | no | discipline, privacy, health, anything delicate? |
| consent_ok | no | all students cleared for photo release? |

**Nobody renames a file, resizes a photo, writes a caption or organizes a
folder.** The automation does all of it.

## Consent and sensitivity

Two protections run automatically:

- `consent_ok=False` blocks the asset from ever reaching an approved state, and
  disqualifies it from paid creative entirely.
- Any description containing sensitive language -- injury, discipline, illness,
  police, custody, funeral and others -- flags the asset as sensitive even when
  the contributor left the box unchecked, and routes approval to the Head of
  School.

Neither can be overridden by the automation. A human clears them or they stand.
