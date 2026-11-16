# Recognition: appreciating operators

The people on the floor keep the plant running, and most of what they do well never shows up in a report. FoaMES gives them a place to thank each other, credits them when their ideas are put into practice, marks their milestones, and points out when a line had a good week. All of it shows on the Floor View.

Recognition is positive by design:

- **It never ranks people.** There is no leaderboard, no "top operator" and no comparison of one person with another. Team highlights are per line, never per person.
- **It never turns a bad result into a record about someone.** A week that went badly simply produces no highlight. FoaMES keeps no per-person performance score.
- **People control their own visibility.** Anyone can keep their name off the Floor View and turn off their own milestones, and a recognition can be marked private.

It is a known practice in lean and operational-excellence programmes (shout-out boards, idea credit in suggestion schemes, safety and quality call-outs); FoaMES just records it next to the floor data it already has.

## Kinds

| Kind | Given by | For |
| --- | --- | --- |
| Kudos | anyone | A general thank-you |
| Helping Hand | anyone | Someone who stepped in to help: covered a station, answered a call, trained a colleague |
| Improvement | anyone, or FoaMES for a credited idea | An improvement someone made or suggested |
| Safety | anyone | A good catch or a safe act |
| Quality | anyone | Catching a defect, holding a suspect lot, getting a process back in control |
| Milestone | FoaMES | A person's own running total reaching a threshold (below) |
| Team Highlight | FoaMES | A line's good week (below) |

A recognition goes to a **person** (a user) or a **team** (a line, shift or crew, named in free text). It can name the machine it happened at and the record it is for, such as the Andon Call someone answered or the Agent Suggestion they carried out.

## Giving one

On the Floor View, **Recognition > Give Kudos** opens a short form: what it is for, the person (leave empty to recognize a whole team), the team, the machine, the message and a **Private** box. The same form is the **Recognition** DocType in the desk, and `give_recognition` in the API.

FoaMES stamps who gave it and when. Nobody can recognize themselves, and people cannot give Milestones or Team Highlights. The person recognized gets an alert in their notifications (turn this off with **Notify the Person Recognized** in Recognition Settings).

Once given, a recognition cannot be edited; it says what it said. The giver or a supervisor can **withdraw** it (Status Withdrawn), which takes it off the floor. The giver, the person recognized or a supervisor can make it private.

## Credited ideas

Agent Suggestions have an **Idea From** field. When an operator's idea becomes a suggestion (typed in by a supervisor, or posted by an agent that heard it), put their name there. When the suggestion is marked **Done**, FoaMES recognizes them with an Improvement recognition, "Your idea was put into practice", linked to the suggestion. This happens once per suggestion, even if it is reopened and closed again.

## Milestones

Once a day FoaMES counts, for each person:

| Count | What counts |
| --- | --- |
| Andon calls answered | Calls they acknowledged, and calls they resolved that someone else had not acknowledged first. Cancelled calls do not count for acknowledging |
| Suggestions carried out | Agent Suggestions they marked Done, except andon escalations (those close when the call is answered, which is already counted) |
| Ideas put into practice | Done suggestions with them as Idea From |

When a count reaches a threshold (by default 1, 10, 25, 50, 100, 250, 500 and 1000; set them in **Milestone Thresholds**), they get a Milestone recognition such as "First andon call answered" or "50 suggestions carried out". Each milestone is given once. When several are reached at once, for example when milestones are first turned on at a busy site, only the highest is given, so nobody receives a burst of messages, and a lower threshold is never given after a higher one.

Milestones count only a person's own contributions and are never compared with anyone else's.

## Team highlights

Every Monday at 06:00, after the daily OEE run has closed Sunday, FoaMES looks at the week that just ended (Monday to Monday) for each line. A machine without a Line is its own team. It reads the line's OEE Periods for that week and the eight before it, and the andon calls raised on its machines, and gives a Team Highlight for each of these that is true:

| Highlight | When |
| --- | --- |
| OEE up | The week's OEE (weighted by planned minutes) is at least **OEE Gain Worth a Highlight** points (default 5) above the last week with enough planned time |
| Best week | The week's OEE is higher than every one of at least four earlier weeks |
| Zero scrap | Good output and no scrap all week |
| Quality up | The quality rate is at least one point above the previous week's, when that was below 100% |
| Help on time | At least three calls for help, every one acknowledged within its call type's target |

A line with less than **Minimum Planned Hours in the Week** (default 8) of planned time gets no OEE or quality highlight; a thin week says too little. Each highlight is given once per line and week. Nothing is ever said about a week that went badly. The rules are pure logic in `foames/foames_mes/recognition.py`.

## On the Floor View

The Floor View shows a **Recognition** section with the recognitions of the last **Show on the Floor For** days (default 7; 0 hides the section), newest first: the kind, who or which team, the machine, the message and who gave it. The floor snapshot carries the same list under `recognitions`, so a SCADA screen or a break-room display can show it too.

What never reaches the floor:

- private recognitions;
- withdrawn recognitions;
- anything about a person who opted out of the floor.

With **Show Names on the Floor** off, people are shown by the team named on the recognition, or as "A teammate", and the giver is not shown.

## Privacy and opting out

**Recognition > My Preferences** on the Floor View lets anyone choose, for themselves:

- **Show my name on the Floor View**: off keeps every recognition of them off the floor. They still see their own recognitions in the desk and in their notifications.
- **Recognize my milestones**: off stops automatic milestones and credited-idea recognitions for them. Kudos from colleagues still arrive.

These land in the **Opted Out** table of Recognition Settings, which supervisors can also edit. The preference calls are `get_my_recognition_preferences` and `set_my_recognition_preferences`; they need no access to the settings.

A **Private** recognition is seen only by the person recognized, the giver, the user who created it and supervisors (FoaMES Supervisor, FoaMES Engineer, System Manager). Everyone else does not see it in lists, reports or the API.

## Settings

**Recognition Settings** (FoaMES Supervisor, FoaMES Engineer, System Manager):

| Field | Default | Meaning |
| --- | --- | --- |
| Show on the Floor For (days) | 7 | How far back the Floor View section goes; 0 hides it |
| Show Names on the Floor | on | Off shows people by team or as "A teammate" |
| Notify the Person Recognized | on | An alert in the recipient's notifications |
| Milestones | on | The daily milestone run |
| Milestone Thresholds | 1,10,25,50,100,250,500,1000 | Comma-separated |
| Team Highlights | on | The weekly team highlight run |
| OEE Gain Worth a Highlight (points) | 5 | For "OEE up" |
| Minimum Planned Hours in the Week | 8 | Below it, a line gets no OEE or quality highlight |
| Opted Out | empty | People who keep their name off the floor, want no milestones, or both |

## Permissions

Operators, supervisors, maintenance and quality can give recognitions and read every recognition that is not private. Only the giver or a supervisor can withdraw one. FoaMES Engineers and System Managers can also delete them.

## API

| Method | Verb | Purpose |
| --- | --- | --- |
| `foames.foames_mes.doctype.recognition.recognition.give_recognition` | POST | `message`, `kind` (default Kudos), `recipient` (a user) or `team`, optional `machine`, `private`, `reference_doctype`, `reference_name` |
| `foames.foames_mes.doctype.recognition.recognition.withdraw_recognition` | POST | `name` |
| `foames.foames_mes.doctype.recognition.recognition.list_recognitions` | GET | Active recognitions of the last `days` days (default 7) the caller may read |
| `foames.foames_mes.doctype.recognition.recognition.get_my_recognition_preferences` | GET | `{"show_on_floor", "milestones"}` for the caller |
| `foames.foames_mes.doctype.recognition.recognition.set_my_recognition_preferences` | POST | `show_on_floor`, `milestones` (1 or 0) for the caller |

An agent may suggest that someone deserves thanks by raising an Agent Suggestion, as with anything else it finds; it does not give recognitions on people's behalf.
