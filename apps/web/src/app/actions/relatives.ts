"use server";

import { refresh } from "next/cache";

import {
  createAssociation,
  createPerson,
  createRelationship,
  deleteAssociation,
  deleteRelationship,
  listPeople,
} from "@/lib/api/endpoints";
import { errorMessageKey, isApiError, type ErrorCode } from "@/lib/api/errors";
import type { PersonSummary } from "@/lib/api/schemas";
import { requireApi } from "@/lib/auth/server";
import {
  asId,
  associationNeedsPhrase,
  defaultSexFor,
  formId,
  isAssociationRole,
  isPartnerStatus,
  isPedigree,
  isRelativeKind,
  PHRASE_MAX,
  relationshipFor,
} from "@/lib/forms/family";
import { readPersonForm, toPersonCreateBody } from "@/lib/forms/person";
import type { EditorState } from "@/lib/forms/types";

import { failedState, field, savedState } from "./editor-result";

/**
 * «Agregar familiar»: links an existing person, or creates one inline and then links them. If
 * the person is created but the link fails, the state says so and points at the new person.
 */
export async function addRelativeAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const personId = formId(form, "personId");
  const spaceId = formId(form, "spaceId");
  const kind = form.get("kind");
  const pedigree = form.get("pedigree");
  const status = form.get("status");
  const mode = form.get("mode") === "new" ? "new" : "existing";
  const fresh = readPersonForm(form);
  const values: Record<string, string> = {
    kind: String(kind ?? ""),
    pedigree: String(pedigree ?? "birth"),
    status: String(status ?? "married"),
    mode,
    given: fresh.given,
    paternal: fresh.paternal,
    maternal: fresh.maternal,
  };
  if (!personId || !spaceId) return { status: "failed", code: "not_found", values };
  if (!isRelativeKind(kind)) return { status: "invalid", error: "kind", values };
  const qualifier = {
    pedigree: isPedigree(pedigree) ? pedigree : "birth",
    status: isPartnerStatus(status) ? status : "married",
  } as const;

  let relativeId = mode === "existing" ? formId(form, "relativeId") : null;
  let createdId: string | undefined;
  if (mode === "existing" && !relativeId) return { status: "invalid", error: "pickRequired", values };
  if (relativeId === personId) return { status: "invalid", error: "samePerson", values };

  const { api } = await requireApi();
  if (mode === "new") {
    const parsed = toPersonCreateBody({ ...fresh, sex: defaultSexFor(kind), birthDate: "", nickname: "" });
    if (!parsed.ok) return { status: "invalid", error: parsed.error, values };
    try {
      relativeId = (await createPerson(api, spaceId, parsed.body)).id;
      createdId = relativeId;
    } catch (error) {
      return failedState(error, values);
    }
  }

  try {
    await createRelationship(api, spaceId, relationshipFor(kind, personId, relativeId as string, qualifier));
  } catch (error) {
    refresh();
    return failedState(error, values, createdId ? { createdId } : {});
  }
  refresh();
  return savedState(previous, createdId);
}

/** Removes one relationship (after the confirmation step in the UI). The people stay. */
export async function removeRelationshipAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const relationshipId = formId(form, "relationshipId");
  if (!relationshipId) return { status: "failed", code: "not_found", values: {} };
  const { api } = await requireApi();
  try {
    await deleteRelationship(api, relationshipId);
  } catch (error) {
    return failedState(error, {});
  }
  refresh();
  return savedState(previous);
}

/** Padrinos, madrinas, testigos u oficiantes on a sacramental event (addendum D). */
export async function addAssociationAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const spaceId = formId(form, "spaceId");
  const eventId = formId(form, "eventId");
  const relativeId = formId(form, "relativeId");
  const role = form.get("role");
  const phrase = field(form, "phrase");
  const values = { role: String(role ?? "godparent"), phrase };
  if (!spaceId || !eventId) return { status: "failed", code: "not_found", values };
  if (!relativeId) return { status: "invalid", error: "pickRequired", values };
  if (!isAssociationRole(role)) return { status: "invalid", error: "role", values };
  if (associationNeedsPhrase(role) && !phrase) return { status: "invalid", error: "phraseRequired", values };
  if (phrase.length > PHRASE_MAX) return { status: "invalid", error: "tooLong", values };

  const { api } = await requireApi();
  try {
    await createAssociation(api, spaceId, {
      event_id: eventId,
      person_id: relativeId,
      role,
      ...(phrase ? { phrase } : {}),
    });
  } catch (error) {
    return failedState(error, values);
  }
  refresh();
  return savedState(previous);
}

export async function removeAssociationAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const associationId = formId(form, "associationId");
  if (!associationId) return { status: "failed", code: "not_found", values: {} };
  const { api } = await requireApi();
  try {
    await deleteAssociation(api, associationId);
  } catch (error) {
    return failedState(error, {});
  }
  refresh();
  return savedState(previous);
}

export type PeopleSearchResult =
  | { ok: true; items: Array<Pick<PersonSummary, "id" | "display_name" | "sex" | "living_status" | "birth">> }
  | { ok: false; code: ErrorCode };

/**
 * The person picker's search. The API matches accents and nicknames (addendum C: «Chucho»
 * finds Jesús); the web only trims and bounds the query.
 */
export async function searchPeopleAction(spaceId: string, query: string): Promise<PeopleSearchResult> {
  const q = query.trim().replace(/\s+/g, " ").slice(0, 120);
  const space = asId(spaceId);
  if (!space) return { ok: false, code: "not_found" };
  if (q.length < 2) return { ok: true, items: [] };
  const { api } = await requireApi();
  try {
    const page = await listPeople(api, space, { q, limit: 10 });
    return {
      ok: true,
      items: page.items.map(({ id, display_name, sex, living_status, birth }) => ({
        id,
        display_name,
        sex,
        living_status,
        birth,
      })),
    };
  } catch (error) {
    if (isApiError(error)) return { ok: false, code: errorMessageKey(error.code) };
    throw error;
  }
}
