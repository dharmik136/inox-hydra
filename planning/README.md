# planning/ is an Obsidian vault

The product plan, drawn as a graph: what the LinkedIn helper reads (Sources),
where it is kept (Entities), what thinks about it (AI), what comes out
(Outputs), what we mean to do with it (Content Plan), what is broken (Gaps),
and how this becomes a product people pay for (Roadmap).

Open it: Obsidian, "Open folder as vault", pick this `planning/` folder. Start
at `00 Home`, then press Ctrl+G for the graph. Each folder has its own colour.

It lives at the repository root, not under `docs/`, on purpose. `docs_engine`
indexes everything under `docs/` into the in-app help search, and these are
internal planning notes, not help for users. Nothing outside `studio/` is
copied into a build, so none of this ships.

Notes link by title (`[[Own Post]]`), so a rename in Obsidian updates every
link. Keep the frontmatter: `type` and `status` are what the graph filters and
the roadmap checklists are read by.
