/**
 * Inox Hydra - Voyager API Schema Registry
 *
 * PURPOSE:
 * This module defines the schemas for intercepting and parsing LinkedIn's internal 
 * Voyager API responses. Since Voyager is an internal, undocumented API, its JSON 
 * structures change frequently (API drift). 
 * 
 * WHY THIS EXISTS:
 * Instead of hardcoding parsing logic across content scripts, we centralize 
 * JSON path definitions here. This allows us to track "drift" (when LinkedIn changes 
 * their response format) by monitoring which optional or required fields fail to extract.
 * When drift is detected, we can deploy a schema update without rewriting the core 
 * extension logic.
 * 
 * DESIGN DECISIONS:
 * - We use RegExp for endpoint matching because LinkedIn frequently appends query 
 *   parameters or version flags to the URL paths.
 * - JSON paths use dot-notation. While full JSONPath evaluation is heavy, our manual
 *   extraction function handles the simple array wildcards `[*]` common in Voyager.
 * - Confidence scoring allows the background script to decide whether to trust the 
 *   extracted data or flag it for manual review in the studio.
 */

// Chrome Extension content scripts do not support ES modules. Everything is
// exposed through a single frozen namespace on window, consumed by content.js.
// The namespace is prefixed to avoid collisions with LinkedIn's own globals.
const SCHEMA_VERSION = "2026.10.1";

/**
 * Registry of known Voyager API endpoint structures.
 * 
 * Keys represent the internal Hydra event type.
 */
const VOYAGER_SCHEMAS = {
  feed_updates: {
    version: SCHEMA_VERSION,
    endpoint: /\/voyager\/api\/feed\/updatesV2/i,
    fields: {
      urn: "elements[*].entityUrn",
      text: "elements[*].commentary.text.text",
      likes: "elements[*].socialDetail.totalSocialActivityCounts.numLikes",
      comments: "elements[*].socialDetail.totalSocialActivityCounts.numComments",
      impressions: "elements[*].socialDetail.totalSocialActivityCounts.numViews"
    },
    required: ["urn"],
    optional: ["text", "likes", "comments", "impressions"],
    extract: (responseJson) => extractFeedUpdates(responseJson)
  },
  
  identity_profiles: {
    version: SCHEMA_VERSION,
    endpoint: /\/(voyager\/api\/identity\/profiles|identity\/dash\/profiles)/i,
    fields: {
      firstName: "elements[*].firstName",
      lastName: "elements[*].lastName",
      headline: "elements[*].headline",
      company: "elements[*].miniProfile.occupation", // Often nested in Voyager
      location: "elements[*].locationName",
      vanity: "elements[*].publicIdentifier"
    },
    required: ["vanity"],
    optional: ["firstName", "lastName", "headline", "company", "location"],
    extract: (responseJson) => extractProfiles(responseJson)
  },

  creator_analytics: {
    version: SCHEMA_VERSION,
    endpoint: /\/voyager\/api\/identity\/dash\/creatorAnalytics/i,
    fields: {
      followers: "elements[*].followerCount",
      impressions: "elements[*].impressionAggregate",
      engagement: "elements[*].engagementRate"
    },
    required: ["followers"],
    optional: ["impressions", "engagement"],
    extract: (responseJson) => extractAnalytics(responseJson)
  },

  social_actions: {
    version: SCHEMA_VERSION,
    endpoint: /\/voyager\/api\/socialActions/i,
    fields: {
      actorUrn: "elements[*].actor.urn",
      reactionType: "elements[*].reactionType",
      actorName: "elements[*].actor.name"
    },
    required: ["actorUrn"],
    optional: ["reactionType", "actorName"],
    extract: (responseJson) => extractSocialActions(responseJson)
  },

  feed_comments: {
    version: SCHEMA_VERSION,
    endpoint: /\/voyager\/api\/feed\/comments/i,
    fields: {
      commenterName: "elements[*].commenter.name",
      commenterHeadline: "elements[*].commenter.headline",
      commenterProfileUrl: "elements[*].commenter.publicIdentifier",
      text: "elements[*].comment.values[*].value"
    },
    required: ["commenterName", "text"],
    optional: ["commenterHeadline", "commenterProfileUrl"],
    extract: (responseJson) => extractComments(responseJson)
  }
};

/**
 * Helper function to extract fields from feed updates based on the schema mapping.
 * (Simplified for structural extraction).
 */
function extractFeedUpdates(json) {
    const data = [];
    if (json && Array.isArray(json.elements)) {
        for (const el of json.elements) {
            data.push({
                urn: el.entityUrn,
                text: el.commentary?.text?.text,
                likes: el.socialDetail?.totalSocialActivityCounts?.numLikes,
                comments: el.socialDetail?.totalSocialActivityCounts?.numComments,
                impressions: el.socialDetail?.totalSocialActivityCounts?.numViews
            });
        }
    }
    return data;
}

function extractProfiles(json) {
    const data = [];
    const elements = Array.isArray(json.elements) ? json.elements : [json];
    for (const el of elements) {
        if (!el) continue;
        data.push({
            firstName: el.firstName,
            lastName: el.lastName,
            headline: el.headline,
            company: el.miniProfile?.occupation,
            location: el.locationName,
            vanity: el.publicIdentifier
        });
    }
    return data;
}

function extractAnalytics(json) {
    const data = [];
    if (json && Array.isArray(json.elements)) {
        for (const el of json.elements) {
            data.push({
                followers: el.followerCount,
                impressions: el.impressionAggregate,
                engagement: el.engagementRate
            });
        }
    }
    return data;
}

function extractSocialActions(json) {
    const data = [];
    if (json && Array.isArray(json.elements)) {
        for (const el of json.elements) {
            data.push({
                actorUrn: el.actor?.urn,
                reactionType: el.reactionType,
                actorName: el.actor?.name
            });
        }
    }
    return data;
}

function extractComments(json) {
    const data = [];
    if (json && Array.isArray(json.elements)) {
        for (const el of json.elements) {
            const textVals = el.comment?.values || [];
            const text = textVals.map(v => v.value).join(" ");
            data.push({
                commenterName: el.commenter?.name,
                commenterHeadline: el.commenter?.headline,
                commenterProfileUrl: el.commenter?.publicIdentifier,
                text: text || undefined
            });
        }
    }
    return data;
}

/**
 * Resolves a given URL to a known Voyager schema.
 * 
 * WHY:
 * We need to quickly determine if an intercepted network request matches 
 * an endpoint we care about before attempting heavy parsing.
 * 
 * @param {string} url - The intercepted request URL
 * @returns {object|null} The matching schema object or null if unknown.
 */
function resolveSchema(url) {
    if (!url || typeof url !== 'string') return null;
    
    for (const key in VOYAGER_SCHEMAS) {
        const schema = VOYAGER_SCHEMAS[key];
        if (schema.endpoint.test(url)) {
            return schema;
        }
    }
    return null;
}

/**
 * Extracts data from a JSON payload using the provided schema.
 * Calculates confidence and detects API drift by checking for missing required/optional fields.
 * 
 * WHY:
 * Instead of throwing hard errors when LinkedIn updates their API, we fail gracefully.
 * Returning `drift` lists allows our backend telemetry to flag when schemas need 
 * updating, without completely breaking the user experience if only optional fields 
 * are missing.
 * 
 * @param {object} schema - The resolved schema object
 * @param {object} json - The parsed JSON response body from Voyager
 * @returns {object} Extraction result { success, data, drift, confidence, schema_version }
 */
function extractWithSchema(schema, json) {
    if (!schema || !json) {
        return {
            success: false,
            data: null,
            drift: ['INVALID_INPUT'],
            confidence: 0.0,
            schema_version: schema?.version || SCHEMA_VERSION
        };
    }

    let extractedData = null;
    try {
        extractedData = schema.extract(json);
    } catch (err) {
        return {
            success: false,
            data: null,
            drift: ['EXTRACTION_CRASH'],
            confidence: 0.0,
            schema_version: schema.version
        };
    }
    
    const drift = [];
    let requiredMissing = false;
    let optionalMissing = false;

    const dataArray = Array.isArray(extractedData) ? extractedData : [extractedData];
    
    if (dataArray.length > 0) {
        const sample = dataArray[0];
        
        for (const reqField of schema.required) {
            if (sample[reqField] === undefined || sample[reqField] === null) {
                requiredMissing = true;
                drift.push(schema.fields[reqField] || reqField);
            }
        }

        for (const optField of schema.optional) {
            if (sample[optField] === undefined || sample[optField] === null) {
                optionalMissing = true;
                drift.push(schema.fields[optField] || optField);
            }
        }
    }

    let confidence = 1.0;
    let success = true;

    if (requiredMissing) {
        success = false;
        confidence = 0.0;
    } else if (optionalMissing) {
        confidence = 0.8;
    }

    return {
        success,
        data: extractedData,
        drift,
        confidence,
        schema_version: schema.version
    };
}

// Expose as a frozen namespace for consumption by content.js.
// Frozen so that nothing on the LinkedIn page can tamper with the schemas.
window.__InoxVoyagerSchema = Object.freeze({
    SCHEMA_VERSION,
    VOYAGER_SCHEMAS,
    resolveSchema,
    extractWithSchema
});
