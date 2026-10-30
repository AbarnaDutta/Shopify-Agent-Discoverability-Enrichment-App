// app/routes/app.issues.jsx

import {
  useEffect,
  useMemo,
  useState,
  Fragment,
} from "react";
import PropTypes from "prop-types";

import {
  useFetcher,
  useNavigate,
  useRouteLoaderData,
} from "react-router";

import {
  Search,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Wrench,
  X,
  LoaderCircle,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function getPriority(value) {
  const priority = String(value || "medium").toLowerCase();
  if (["high", "medium", "low"].includes(priority)) {
    return priority;
  }
  return "medium";
}

function getAffectedProducts(recommendation, products) {
  const ids = Array.isArray(recommendation?.affected_product_ids)
    ? recommendation.affected_product_ids.map(String)
    : [];

  if (ids.length === 0) {
    return [];
  }

  return products.filter((product) =>
    ids.includes(String(product.product_id))
  );
}

function prettyLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

// FastAPI can return `detail` as a string or as an array of validation errors.
function toMessage(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => item?.msg || (typeof item === "string" ? item : JSON.stringify(item)))
      .join("; ");
  }
  if (typeof value === "object") return value.message || JSON.stringify(value);
  return String(value);
}

const STORE_CHECK_LABELS = {
  fulfillment_context: "Shipping & Fulfillment",
  faq_or_guidance: "FAQ & Help Content",
  legal_pages: "Legal Pages",
  policy_semantics: "Policy Semantics",
  store_guardrails: "Store Guardrails",
  contact_brand: "Contact & Brand Information",
  consistency: "Catalog Consistency",
};

// Keep aligned with app/services/issue_registry.py.
const REGISTERED_FIX_ACTIONS = {
  faq_or_guidance: {
    missing_faq: "create_faq",
    insufficient_shopping_guidance: "create_faq",
  },
  fulfillment_context: {
    missing_delivery_time: "update_fulfillment_information",
    missing_shipping_methods: "update_fulfillment_information",
    missing_pickup_information: "update_fulfillment_information",
    missing_region_coverage: "update_fulfillment_information",
  },
  policy_semantics: {
    placeholder_in_policy: "update_policy",
    missing_policy_deadline: "update_policy",
    missing_policy_exception: "update_policy",
    missing_policy_region: "update_policy",
    ambiguous_policy_rule: "update_policy",
  },
  legal_pages: {
    missing_privacy_policy: "update_policy",
    missing_refund_policy: "update_policy",
    missing_shipping_policy: "update_policy",
    missing_terms_policy: "update_policy",
    placeholder_privacy_policy: "update_policy",
    placeholder_refund_policy: "update_policy",
    placeholder_shipping_policy: "update_policy",
    placeholder_terms_policy: "update_policy",
  },
  contact_brand: {
    missing_contact_information: "update_store_contact",
    missing_brand_information: "update_brand_information",
  },
  store_guardrails: {
    missing_age_gating: "configure_store_guardrail",
    missing_manual_approval_rule: "configure_store_guardrail",
  },
  consistency: {
    inconsistent_option_structure: "normalize_option_structure",
    inconsistent_metafield_structure: "normalize_metafield_structure",
    inconsistent_attribute_format: "normalize_attribute_formats",
    inconsistent_attribute_units: "normalize_attribute_units",
  },
};

const POLICY_TYPE_BY_ISSUE = {
  missing_privacy_policy: "PRIVACY_POLICY",
  placeholder_privacy_policy: "PRIVACY_POLICY",
  missing_refund_policy: "REFUND_POLICY",
  placeholder_refund_policy: "REFUND_POLICY",
  missing_shipping_policy: "SHIPPING_POLICY",
  placeholder_shipping_policy: "SHIPPING_POLICY",
  missing_terms_policy: "TERMS_OF_SERVICE",
  placeholder_terms_policy: "TERMS_OF_SERVICE",
};

// If every issue registered under a check uses the same fix action
// (e.g. all legal_pages issues -> update_policy), the form can be shown
// before the merchant picks the exact issue.
function sharedActionForCheck(checkId) {
  const actions = Object.values(REGISTERED_FIX_ACTIONS[checkId] || {});
  const unique = [...new Set(actions)];
  return unique.length === 1 ? unique[0] : "";
}

const POLICY_KEYWORDS = [
  ["privacy_policy", /privacy/],
  ["refund_policy", /refund|return/],
  ["shipping_policy", /shipping policy|shipping and delivery policy/],
  ["terms_policy", /terms|\btos\b/],
];

function detectPolicyKeys(text) {
  const value = String(text || "").toLowerCase();
  return POLICY_KEYWORDS.filter(([, pattern]) => pattern.test(value)).map(([key]) => key);
}

// Narrow legal_pages candidates (missing_* / placeholder_* for 4 policies)
// using the recommendation text. Only narrows when the text is unambiguous.
function narrowLegalCandidates(candidates, label, text) {
  let result = candidates;

  let keys = detectPolicyKeys(label);
  if (keys.length !== 1) keys = detectPolicyKeys(text);
  if (keys.length === 1) {
    const narrowed = result.filter((issue) =>
      String(issue.issue_type).endsWith(`_${keys[0]}`)
    );
    if (narrowed.length) result = narrowed;
  }

  if (result.length > 1) {
    const value = `${label} ${text}`.toLowerCase();
    const wantsPlaceholder = /placeholder|lorem|boilerplate|default text|template text/.test(value);
    const wantsMissing = /\bmissing\b|not set|not found|does not have|no .* policy/.test(value);
    if (wantsPlaceholder !== wantsMissing) {
      const prefix = wantsPlaceholder ? "placeholder_" : "missing_";
      const narrowed = result.filter((issue) => String(issue.issue_type).startsWith(prefix));
      if (narrowed.length) result = narrowed;
    }
  }

  return result;
}

function resolveStoreFixMetadata(recommendation, auditIssues) {
  const storeIssues = Array.isArray(auditIssues)
    ? auditIssues
        .map((issue) => ({
          ...issue,
          issue_id: issue?.issue_id ?? issue?.audit_issue_id ?? issue?.id ?? "",
          check_id: issue?.check_id ?? issue?.checkId ?? "",
          issue_type: issue?.issue_type ?? issue?.issueType ?? issue?.type ?? "",
        }))
        .filter((issue) => {
          const scope = String(issue?.scope || "").toLowerCase().replaceAll("_", "-");
          const storeScope = ["store", "store-wide", "storewide", "store-level"].includes(scope);
          const missingScopeButClearlyStore = !scope && Boolean(issue.check_id) && !issue.product_id;
          return storeScope || missingScopeButClearlyStore;
        })
    : [];

  const suppliedFix = recommendation?.fix_payload || {};
  const recommendationText = [
    recommendation?.enrichment,
    recommendation?.example,
    recommendation?.description,
    recommendation?.why_it_matters_for_agents,
    recommendation?.recommendation,
  ].filter(Boolean).join(" ").toLowerCase();
  const label = String(recommendation?.enrichment || "").trim().toLowerCase();

  const labelMatches = storeIssues.filter((issue) => {
    const issueLabel = String(
      issue?.check_label || issue?.label || STORE_CHECK_LABELS[issue?.check_id] || prettyLabel(issue?.check_id)
    ).trim().toLowerCase();
    return issueLabel && label && (issueLabel === label || label.includes(issueLabel) || issueLabel.includes(label));
  });

  let checkId = recommendation?.check_id || suppliedFix.check_id || "";
  if (!checkId) {
    const labelChecks = [...new Set(labelMatches.map((issue) => issue.check_id).filter(Boolean))];
    if (labelChecks.length === 1) checkId = labelChecks[0];
  }
  if (!checkId) {
    // Only use known check vocabulary when that check exists in the returned audit.
    // If the text fits more than one check, leave checkId empty so the merchant chooses.
    const availableChecks = new Set(storeIssues.map((issue) => issue.check_id).filter(Boolean));
    const text = recommendationText;
    const likelyChecks = [];
    if (/faq|help page|shopping guidance|fewer than 30 words/.test(text)) likelyChecks.push("faq_or_guidance");
    if (/privacy|refund|return policy|terms of service|terms policy|legal page/.test(text)) likelyChecks.push("legal_pages");
    if (/shipping policy/.test(text)) likelyChecks.push("legal_pages", "fulfillment_context");
    if (/shipping|delivery|fulfillment|pickup/.test(text.replace(/shipping policy/g, ""))) likelyChecks.push("fulfillment_context");
    if (/contact information|about page|brand information|address/.test(text)) likelyChecks.push("contact_brand");
    if (/guardrail|store disclosure/.test(text)) likelyChecks.push("store_guardrails");
    const validLikelyChecks = [...new Set(likelyChecks.filter((id) => availableChecks.has(id)))];
    if (validLikelyChecks.length === 1) checkId = validLikelyChecks[0];
  }

  // Resolve a candidate using actual audit metadata first, then the text of the
  // recommendation. Never invent an ID.
  let candidates = storeIssues.filter((issue) => !checkId || issue.check_id === checkId);
  const explicitType = recommendation?.issue_type || suppliedFix.issue_type || "";
  if (explicitType) candidates = candidates.filter((issue) => issue.issue_type === explicitType);

  if (!explicitType && checkId === "legal_pages" && candidates.length > 1) {
    candidates = narrowLegalCandidates(candidates, label, recommendationText);
  }

  if (!explicitType && candidates.length > 1 && recommendationText) {
    const stopWords = new Set(["the", "and", "for", "with", "from", "that", "this", "your", "has", "have", "into", "page", "policy", "issue", "store", "text"]);
    const tokens = (value) => String(value || "").toLowerCase().match(/[a-z0-9_]+/g)?.filter((token) => token.length > 3 && !stopWords.has(token)) || [];
    const recommendationTokens = new Set(tokens(recommendationText));
    const ranked = candidates.map((issue) => {
      const issueText = [issue.issue_type, issue.title, issue.name, issue.description, issue.message, issue.recommendation].filter(Boolean).join(" ");
      const overlap = tokens(issueText).filter((token) => recommendationTokens.has(token)).length;
      return { issue, overlap };
    }).sort((a, b) => b.overlap - a.overlap);
    if (ranked.length && ranked[0].overlap > 0 && (ranked.length === 1 || ranked[0].overlap > ranked[1].overlap)) {
      candidates = [ranked[0].issue];
    }
  }

  if (!checkId && candidates.length === 1) checkId = candidates[0].check_id || "";
  let issueType = explicitType || (candidates.length === 1 ? candidates[0].issue_type || "" : "");

  const explicitIssueId = recommendation?.issue_id || recommendation?.id || suppliedFix.issue_id || "";
  let issueId = explicitIssueId ? String(explicitIssueId) : "";
  let matchingIssue = null;
  if (issueId) {
    matchingIssue = storeIssues.find((issue) => String(issue.issue_id || issue.id || "") === issueId) || null;
  } else {
    const exactCandidates = storeIssues.filter((issue) =>
      (!checkId || issue.check_id === checkId) &&
      (!issueType || issue.issue_type === issueType) &&
      (issue.issue_id || issue.id)
    );
    if (exactCandidates.length === 1) {
      matchingIssue = exactCandidates[0];
      issueId = String(matchingIssue.issue_id || matchingIssue.id);
    } else if (candidates.length === 1 && (candidates[0].issue_id || candidates[0].id)) {
      matchingIssue = candidates[0];
      issueId = String(matchingIssue.issue_id || matchingIssue.id);
    }
  }

  if (matchingIssue) {
    checkId = checkId || matchingIssue.check_id || "";
    issueType = issueType || matchingIssue.issue_type || "";
  }

  const fixAction =
    recommendation?.fix_action ||
    suppliedFix.fix_action ||
    matchingIssue?.fix_action ||
    REGISTERED_FIX_ACTIONS[checkId]?.[issueType] ||
    sharedActionForCheck(checkId) ||
    "";

  // Offer ALL store issues so a wrong guess can always be corrected.
  // Issues from the guessed check are listed first.
  const rank = (issue) => (checkId && issue.check_id === checkId ? 0 : 1);
  const store_issues = storeIssues
    .filter((issue) => issue.issue_id)
    .sort((a, b) => rank(a) - rank(b))
    .map((issue) => ({
      issue_id: String(issue.issue_id),
      check_id: issue.check_id,
      issue_type: issue.issue_type,
      label: prettyLabel(issue.issue_type),
      fix_action:
        issue.fix_action || REGISTERED_FIX_ACTIONS[issue.check_id]?.[issue.issue_type] || "",
    }));

  const supplied = Boolean(
    (recommendation?.check_id || suppliedFix.check_id) &&
    (recommendation?.issue_type || suppliedFix.issue_type) &&
    (recommendation?.issue_id || suppliedFix.issue_id)
  );

  return {
    check_id: checkId,
    issue_type: issueType,
    issue_id: issueId,
    fix_action: fixAction,
    store_issues,
    supplied,
  };
}

/* -------------------------------------------------------------------------- */
/* Severity badge                                                             */
/* -------------------------------------------------------------------------- */

function SeverityBadge({ priority }) {
  const severity = getPriority(priority);
  const styles = {
    high: "border-[#FFC9C5] bg-[#FFF0EF] text-[#D72C0D]",
    medium: "border-[#FFE0A3] bg-[#FFF5E5] text-[#8A6116]",
    low: "border-[#E1E3E5] bg-[#F1F2F3] text-[#6D7175]",
  };

  const dotStyles = {
    high: "bg-[#D72C0D]",
    medium: "bg-[#FFB100]",
    low: "bg-[#6D7175]",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${styles[severity]}`}
    >
      <span className={`h-2 w-2 rounded-full ${dotStyles[severity]}`} />
      {prettyLabel(severity)}
    </span>
  );
}

SeverityBadge.propTypes = {
  priority: PropTypes.string,
};

/* -------------------------------------------------------------------------- */
/* Store-wide fix modal                                                       */
/* -------------------------------------------------------------------------- */

function StoreFixModal({ issue, shopDomain, onClose }) {
  const fetcher = useFetcher();
  const recommendation = issue.raw || {};
  const suppliedFix = recommendation.fix_payload || {};

  // Candidate store issues (same idea as the product page, where each fixable
  // issue carries its own id / check_id / issue_type).
  const issueOptions = Array.isArray(recommendation.store_issues)
    ? recommendation.store_issues
    : [];

  const resolvedCheckId = recommendation.check_id || suppliedFix.check_id || "";
  const resolvedIssueType = recommendation.issue_type || suppliedFix.issue_type || "";
  const resolvedIssueId = recommendation.issue_id || suppliedFix.issue_id || "";

  // Show the picker whenever the IDs were inferred from text rather than
  // supplied by the backend.
  const needsPicker = issueOptions.length > 1 && !recommendation.metadata_supplied;

  const [pickedIssueId, setPickedIssueId] = useState(() =>
    issueOptions.some((option) => option.issue_id === resolvedIssueId)
      ? resolvedIssueId
      : issueOptions.length === 1
        ? issueOptions[0].issue_id
        : ""
  );
  const pickedIssue = issueOptions.find((option) => option.issue_id === pickedIssueId);

  const checkId = pickedIssue?.check_id || resolvedCheckId;
  const issueType = pickedIssue?.issue_type || resolvedIssueType;
  const initialIssueId = pickedIssue?.issue_id || resolvedIssueId;

  const fixAction =
    pickedIssue?.fix_action ||
    recommendation.fix_action ||
    suppliedFix.fix_action ||
    REGISTERED_FIX_ACTIONS[checkId]?.[issueType] ||
    sharedActionForCheck(checkId) ||
    "";

  const initialChanges =
    recommendation.changes ??
    suppliedFix.changes ??
    [];

  const [changesText, setChangesText] = useState(() =>
    JSON.stringify(initialChanges, null, 2)
  );
  const [faqPageId, setFaqPageId] = useState(
    String(suppliedFix.page_id || initialChanges?.[0]?.page_id || "")
  );
  const [faqTitle, setFaqTitle] = useState(
    String(suppliedFix.title || initialChanges?.[0]?.title || "Frequently Asked Questions")
  );
  const [faqBody, setFaqBody] = useState(
    String(suppliedFix.body || initialChanges?.[0]?.body || "")
  );
  const [faqPublish, setFaqPublish] = useState(
    Boolean(suppliedFix.publish ?? initialChanges?.[0]?.publish ?? false)
  );
  const [policyType, setPolicyType] = useState(
    String(
      suppliedFix.policy_type ||
        initialChanges?.[0]?.policy_type ||
        POLICY_TYPE_BY_ISSUE[issueType] ||
        "REFUND_POLICY"
    )
  );
  const [merchantBody, setMerchantBody] = useState(String(suppliedFix.body || initialChanges?.[0]?.body || ""));
  const [merchantApproved, setMerchantApproved] = useState(Boolean(suppliedFix.merchant_approved ?? initialChanges?.[0]?.merchant_approved ?? false));
  const [warningText, setWarningText] = useState(String(suppliedFix.warning_text || initialChanges?.[0]?.warning_text || ""));
  const [shippingPolicyBody, setShippingPolicyBody] = useState(String(suppliedFix.shipping_policy_body || initialChanges?.[0]?.shipping_policy_body || ""));
  const [deliveryProfileId, setDeliveryProfileId] = useState(String(suppliedFix.delivery_profile_id || initialChanges?.[0]?.delivery_profile_id || ""));
  const [deliveryProfileUpdateText, setDeliveryProfileUpdateText] = useState(() => JSON.stringify(suppliedFix.delivery_profile_update || initialChanges?.[0]?.delivery_profile_update || {}, null, 2));
  const [pickupSettingsText, setPickupSettingsText] = useState(() => JSON.stringify(suppliedFix.pickup_settings || initialChanges?.[0]?.pickup_settings || [], null, 2));

  // Keep the policy type in sync with the selected legal issue.
  const lockedPolicyType = POLICY_TYPE_BY_ISSUE[issueType] || "";
  useEffect(() => {
    if (lockedPolicyType) setPolicyType(lockedPolicyType);
  }, [lockedPolicyType]);

  const isFaqGuidance = ["create_faq", "update_faq_guidance"].includes(fixAction) || checkId === "faq_or_guidance";
  const isPolicyFix = fixAction === "update_policy";
  const isContactFix = fixAction === "update_store_contact";
  const isBrandPageFix = fixAction === "update_brand_information";
  const isGuardrailFix = fixAction === "configure_store_guardrail";
  const isFulfillmentFix = fixAction === "update_fulfillment_information";
  const isStructuredPageFix = isFaqGuidance || isBrandPageFix;

  const [validationError, setValidationError] = useState("");
  const isSubmitting = fetcher.state !== "idle";
  const responseData = fetcher.data;
  const requestSucceeded =
    responseData?.success === true ||
    responseData?.data?.success === true;

  const requestFailed =
    responseData &&
    !isSubmitting &&
    !requestSucceeded &&
    (
      responseData.success === false ||
      responseData.ok === false ||
      Boolean(responseData.error) ||
      Boolean(responseData.detail)
    );

  const responseMessage =
    toMessage(responseData?.message) ||
    toMessage(responseData?.detail) ||
    toMessage(responseData?.error) ||
    toMessage(responseData?.data?.message) ||
    toMessage(responseData?.data?.detail) ||
    "";

  // Group picker options by check so a wrong guess is easy to correct.
  const groupedOptions = issueOptions.reduce((groups, option) => {
    const group = STORE_CHECK_LABELS[option.check_id] || prettyLabel(option.check_id);
    (groups[group] ||= []).push(option);
    return groups;
  }, {});

  const parseChanges = () => {
    let parsedChanges;
    try {
      parsedChanges = JSON.parse(changesText);
    } catch {
      throw new Error(
        "Changes must be valid JSON. Check the brackets, commas, and quotation marks."
      );
    }

    if (!Array.isArray(parsedChanges) || parsedChanges.length === 0) {
      throw new Error(
        "Enter a non-empty JSON array containing the actual changes to apply."
      );
    }

    if (
      parsedChanges.some(
        (change) =>
          !change ||
          typeof change !== "object" ||
          Array.isArray(change)
      )
    ) {
      throw new Error("Every item in changes must be a JSON object.");
    }

    return parsedChanges;
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setValidationError("");

    if (!shopDomain) {
      setValidationError(
        "The Shopify store domain is missing. Reload the app and try again."
      );
      return;
    }

    if (needsPicker && !pickedIssue) {
      setValidationError("Select which audit issue you are fixing.");
      return;
    }
    if (!checkId.trim()) {
      setValidationError(
        "The check ID could not be determined. Select the audit issue above."
      );
      return;
    }
    if (!issueType.trim()) {
      setValidationError(
        "The issue type could not be determined. Select the audit issue above."
      );
      return;
    }
    if (!initialIssueId.trim()) {
      setValidationError(
        "The store-wide audit issue ID is missing or ambiguous. Refresh the audit and select the specific store issue."
      );
      return;
    }

    let changes;

    if (isStructuredPageFix) {
      if (!faqBody.trim()) {
        setValidationError("Enter the complete page content you have reviewed before applying the fix.");
        return;
      }
      if (faqPageId.trim() && !/^gid:\/\/shopify\/Page\/[0-9]+$/.test(faqPageId.trim())) {
        setValidationError("If you provide a page ID, use the Shopify Page GID format: gid://shopify/Page/123456789.");
        return;
      }
      changes = [{
        ...(faqPageId.trim() ? { page_id: faqPageId.trim() } : {}),
        body: faqBody.trim(),
        merchant_approved: true,
        ...(faqTitle.trim() ? { title: faqTitle.trim() } : {}),
        publish: faqPublish,
      }];
    } else if (isPolicyFix) {
      if (!merchantBody.trim()) {
        setValidationError("Enter the complete policy text you have reviewed.");
        return;
      }
      if (!merchantApproved) {
        setValidationError("Confirm that you reviewed and approved the replacement policy text.");
        return;
      }
      changes = [{ policy_type: policyType, body: merchantBody.trim(), merchant_approved: true }];
    } else if (isContactFix) {
      if (!merchantBody.trim() || !merchantApproved) {
        setValidationError("Enter the complete contact information and confirm that you approved it.");
        return;
      }
      changes = [{ body: merchantBody.trim(), merchant_approved: true }];
    } else if (isGuardrailFix) {
      if (!warningText.trim() || !merchantApproved) {
        setValidationError("Enter the approved store disclosure and confirm that it is accurate.");
        return;
      }
      changes = [{ warning_text: warningText.trim(), merchant_approved: true }];
    } else if (isFulfillmentFix) {
      const change = {};
      if (shippingPolicyBody.trim()) change.shipping_policy_body = shippingPolicyBody.trim();
      if (deliveryProfileId.trim()) {
        let deliveryProfileUpdate;
        try { deliveryProfileUpdate = JSON.parse(deliveryProfileUpdateText); }
        catch { setValidationError("Delivery profile update must be valid JSON."); return; }
        if (!deliveryProfileUpdate || typeof deliveryProfileUpdate !== "object" || Array.isArray(deliveryProfileUpdate) || !Object.keys(deliveryProfileUpdate).length) {
          setValidationError("Provide a non-empty delivery profile update object when using a delivery profile ID."); return;
        }
        change.delivery_profile_id = deliveryProfileId.trim();
        change.delivery_profile_update = deliveryProfileUpdate;
      }
      let pickupSettings;
      try { pickupSettings = JSON.parse(pickupSettingsText); }
      catch { setValidationError("Pickup settings must be valid JSON."); return; }
      if (!Array.isArray(pickupSettings)) { setValidationError("Pickup settings must be a JSON array."); return; }
      if (pickupSettings.length) change.pickup_settings = pickupSettings;
      if (!Object.keys(change).length) { setValidationError("Enter at least one shipping policy, delivery profile, or pickup update."); return; }
      changes = [change];
    } else {
      try {
        changes = parseChanges();
      } catch (error) {
        setValidationError(error.message);
        return;
      }
    }

    /*
     * Uses the existing authenticated action in app.products.detail.jsx, which
     * injects the session's shop_domain and access_token and forwards the
     * request to POST /store/fix (same path the product fixes use).
     */
    fetcher.submit(
      {
        __endpoint: "/store/fix",
        shop_domain: shopDomain,
        issue_id: initialIssueId.trim(),
        check_id: checkId.trim(),
        issue_type: issueType.trim(),
        changes,
      },
      {
        method: "post",
        action: "/app/products/detail",
        encType: "application/json",
      }
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="store-fix-title"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-[#E1E3E5] bg-white shadow-xl"
      >
        {/* Modal header */}
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#E1E3E5] bg-white p-5">
          <div>
            <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-[#FFF5E5] text-[#8A6116]">
              <Wrench className="h-4 w-4" />
            </div>

            <h2 id="store-fix-title" className="text-base font-bold text-[#202223]">
              Fix store-wide issue
            </h2>

            <p className="mt-1 text-xs text-[#6D7175]">
              Review the request before applying changes to your Shopify store.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close fix dialog"
            className="rounded-md p-2 text-[#6D7175] hover:bg-[#F1F2F3] disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-5">
          {/* Issue details */}
          <div className="rounded-lg border border-[#E1E3E5] bg-[#FAFAFA] p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                Audit recommendation
              </span>
              <SeverityBadge priority={issue.priority} />
            </div>

            <h3 className="text-sm font-semibold text-[#202223]">
              Recommendation
            </h3>
            <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-[#6D7175]">
              {recommendation.example ||
                issue.example ||
                recommendation.description ||
                "No recommendation description available."}
            </p>

            <div className="mt-3 text-xs text-[#6D7175]">
              Store:{" "}
              <span className="font-semibold text-[#202223]">
                {shopDomain || "Unavailable"}
              </span>
            </div>

            <div className="mt-1 text-xs text-[#6D7175]">
              Affected products:{" "}
              <span className="font-semibold text-[#202223]">
                {issue.affectedProducts.length}
              </span>
            </div>

            {issue.affectedProducts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {issue.affectedProducts.map((product) => (
                  <span
                    key={product.product_id}
                    className="rounded-full border border-[#E1E3E5] bg-white px-2.5 py-1 text-[11px] text-[#4A5568]"
                  >
                    {product.title || String(product.product_id)}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Issue picker: shown when the IDs were inferred instead of supplied by the backend. */}
          {needsPicker && (
            <div>
              <label htmlFor="store-fix-issue-picker" className="mb-1.5 block text-xs font-semibold text-[#202223]">
                Audit issue to fix
              </label>
              <select
                id="store-fix-issue-picker"
                value={pickedIssueId}
                onChange={(event) => setPickedIssueId(event.target.value)}
                disabled={isSubmitting || requestSucceeded}
                className="w-full rounded-md border border-[#E1E3E5] bg-white px-3 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60"
              >
                <option value="">Choose the issue you are fixing…</option>
                {Object.entries(groupedOptions).map(([group, options]) => (
                  <optgroup key={group} label={group}>
                    {options.map((option) => (
                      <option key={option.issue_id} value={option.issue_id}>
                        {option.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <p className="mt-1 text-[10px] text-[#6D7175]">
                Choosing an issue fills the Check ID, Issue type and Issue ID below and shows the matching form.
              </p>
            </div>
          )}

          {/* Store issue identifiers: analogous to Product Fix metadata, but no product_id. */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="store-fix-issue-id" className="mb-1.5 block text-xs font-semibold text-[#202223]">Issue ID</label>
              <input id="store-fix-issue-id" type="text" value={initialIssueId} readOnly placeholder="Provided by audit metadata" className="w-full rounded-md border border-[#E1E3E5] bg-[#F1F2F3] px-3 py-2 text-xs" />
              <p className="mt-1 text-[10px] text-[#6D7175]">Identifies this store issue.</p>
            </div>
            <div>
              <label htmlFor="store-fix-check-id" className="mb-1.5 block text-xs font-semibold text-[#202223]">Check ID</label>
              <input id="store-fix-check-id" type="text" value={checkId} readOnly placeholder="Provided by audit metadata" className="w-full rounded-md border border-[#E1E3E5] bg-[#F1F2F3] px-3 py-2 text-xs" />
              <p className="mt-1 text-[10px] text-[#6D7175]">Registered backend check.</p>
            </div>
            <div>
              <label htmlFor="store-fix-issue-type" className="mb-1.5 block text-xs font-semibold text-[#202223]">Issue type</label>
              <input id="store-fix-issue-type" type="text" value={issueType} readOnly placeholder="Provided by audit metadata" className="w-full rounded-md border border-[#E1E3E5] bg-[#F1F2F3] px-3 py-2 text-xs" />
              <p className="mt-1 text-[10px] text-[#6D7175]">Registered issue type.</p>
            </div>
          </div>

          {/* Action-specific store fix inputs. */}
          {isStructuredPageFix ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-[#FFE0A3] bg-[#FFF9ED] p-3 text-xs leading-relaxed text-[#805B18]">
                {faqPageId.trim()
                  ? "The selected Shopify page will be updated with the content you approve."
                  : "No existing page is required. A new page will be created using the title and content below."}
                {" "}The app will not invent policy or customer-facing facts.
              </div>
              <div>
                <label htmlFor="store-fix-faq-page-id" className="mb-1.5 block text-xs font-semibold text-[#202223]">Existing Shopify Page ID (optional)</label>
                <input id="store-fix-faq-page-id" value={faqPageId} onChange={(event) => setFaqPageId(event.target.value)} disabled={isSubmitting || requestSucceeded} placeholder="Leave blank to create a new page" className="w-full rounded-md border border-[#E1E3E5] bg-white px-3 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60" />
              </div>
              <div>
                <label htmlFor="store-fix-faq-title" className="mb-1.5 block text-xs font-semibold text-[#202223]">Page title</label>
                <input id="store-fix-faq-title" value={faqTitle} onChange={(event) => setFaqTitle(event.target.value)} disabled={isSubmitting || requestSucceeded} required placeholder={isFaqGuidance ? "Frequently Asked Questions" : "About our store"} className="w-full rounded-md border border-[#E1E3E5] bg-white px-3 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60" />
              </div>
              <div>
                <label htmlFor="store-fix-faq-body" className="mb-1.5 block text-xs font-semibold text-[#202223]">Complete {isFaqGuidance ? "FAQ/help" : "page"} content (HTML)</label>
                <textarea id="store-fix-faq-body" value={faqBody} onChange={(event) => setFaqBody(event.target.value)} disabled={isSubmitting || requestSucceeded} required rows={8} spellCheck={false} placeholder="Enter complete, reviewed content..." className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 font-mono text-xs leading-relaxed text-[#202223] outline-none focus:border-[#D97706] disabled:opacity-60" />
              </div>
              <label className="flex items-center gap-2 text-xs text-[#202223]">
                <input type="checkbox" checked={faqPublish} onChange={(event) => setFaqPublish(event.target.checked)} disabled={isSubmitting || requestSucceeded} className="rounded border-[#E1E3E5]" />
                Publish the page after saving
              </label>
              <p className="text-[11px] leading-relaxed text-[#6D7175]">Submitting confirms that you reviewed and approved this content.</p>
            </div>
          ) : isPolicyFix ? (
            <div className="space-y-4">
              <div>
                <label htmlFor="store-fix-policy-type" className="mb-1.5 block text-xs font-semibold text-[#202223]">Policy type</label>
                <select id="store-fix-policy-type" value={policyType} onChange={(event) => setPolicyType(event.target.value)} disabled={isSubmitting || requestSucceeded || Boolean(lockedPolicyType)} className="w-full rounded-md border border-[#E1E3E5] bg-white px-3 py-2 text-xs disabled:opacity-60">
                  <option value="REFUND_POLICY">Refund policy</option>
                  <option value="SHIPPING_POLICY">Shipping policy</option>
                  <option value="PRIVACY_POLICY">Privacy policy</option>
                  <option value="TERMS_OF_SERVICE">Terms of service</option>
                  <option value="LEGAL_NOTICE">Legal notice</option>
                </select>
              </div>
              <div>
                <label htmlFor="store-fix-policy-body" className="mb-1.5 block text-xs font-semibold text-[#202223]">Complete replacement policy text</label>
                <textarea id="store-fix-policy-body" value={merchantBody} onChange={(event) => setMerchantBody(event.target.value)} disabled={isSubmitting || requestSucceeded} required rows={8} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 text-xs leading-relaxed" placeholder="Enter the full policy text you reviewed..." />
              </div>
              <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={merchantApproved} onChange={(event) => setMerchantApproved(event.target.checked)} disabled={isSubmitting || requestSucceeded} /> I reviewed and approve this full policy replacement.</label>
              <p className="text-[11px] text-[#6D7175]">This replaces the entire selected policy.</p>
            </div>
          ) : isContactFix ? (
            <div className="space-y-4">
              <label htmlFor="store-fix-contact-body" className="block text-xs font-semibold">Complete contact information</label>
              <textarea id="store-fix-contact-body" value={merchantBody} onChange={(event) => setMerchantBody(event.target.value)} disabled={isSubmitting || requestSucceeded} required rows={7} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 text-xs" placeholder="Enter verified business contact details..." />
              <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={merchantApproved} onChange={(event) => setMerchantApproved(event.target.checked)} disabled={isSubmitting || requestSucceeded} /> I confirm these contact details are accurate.</label>
            </div>
          ) : isFulfillmentFix ? (
            <div className="space-y-4">
              <div>
                <label htmlFor="store-fix-shipping-policy-body" className="mb-1.5 block text-xs font-semibold">Replacement shipping policy (optional)</label>
                <textarea id="store-fix-shipping-policy-body" value={shippingPolicyBody} onChange={(event) => setShippingPolicyBody(event.target.value)} disabled={isSubmitting || requestSucceeded} rows={5} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 text-xs" placeholder="Enter complete, merchant-approved shipping policy text..." />
              </div>
              <div>
                <label htmlFor="store-fix-delivery-profile-id" className="mb-1.5 block text-xs font-semibold">Delivery profile ID (optional)</label>
                <input id="store-fix-delivery-profile-id" value={deliveryProfileId} onChange={(event) => setDeliveryProfileId(event.target.value)} disabled={isSubmitting || requestSucceeded} className="w-full rounded-md border border-[#E1E3E5] px-3 py-2 text-xs" placeholder="Existing Shopify delivery profile GID" />
                <label htmlFor="store-fix-delivery-profile-update" className="mb-1.5 mt-2 block text-xs font-semibold">Delivery profile update (JSON object)</label>
                <textarea id="store-fix-delivery-profile-update" value={deliveryProfileUpdateText} onChange={(event) => setDeliveryProfileUpdateText(event.target.value)} disabled={isSubmitting || requestSucceeded} rows={3} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 font-mono text-xs" />
              </div>
              <div>
                <label htmlFor="store-fix-pickup-settings" className="mb-1.5 block text-xs font-semibold">Pickup settings (JSON array, optional)</label>
                <textarea id="store-fix-pickup-settings" value={pickupSettingsText} onChange={(event) => setPickupSettingsText(event.target.value)} disabled={isSubmitting || requestSucceeded} rows={3} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 font-mono text-xs" />
              </div>
              <p className="text-[11px] text-[#6D7175]">Only provide values verified for your store. Leave unused sections blank/default.</p>
            </div>
          ) : isGuardrailFix ? (
            <div className="space-y-4">
              <label htmlFor="store-fix-warning-text" className="block text-xs font-semibold">Store disclosure / warning text</label>
              <textarea id="store-fix-warning-text" value={warningText} onChange={(event) => setWarningText(event.target.value)} disabled={isSubmitting || requestSucceeded} required rows={6} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 text-xs" placeholder="Enter the approved store disclosure..." />
              <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={merchantApproved} onChange={(event) => setMerchantApproved(event.target.checked)} disabled={isSubmitting || requestSucceeded} /> I approve this disclosure.</label>
            </div>
          ) : (
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <label htmlFor="store-fix-changes" className="block text-xs font-semibold text-[#202223]">Changes payload</label>
                <span className="text-[10px] text-[#6D7175]">JSON array</span>
              </div>
              <textarea id="store-fix-changes" value={changesText} onChange={(event) => setChangesText(event.target.value)} disabled={isSubmitting || requestSucceeded} required rows={10} spellCheck={false} className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 font-mono text-xs leading-relaxed text-[#202223] outline-none focus:border-[#D97706] disabled:opacity-60" placeholder={"Enter actual change objects as a JSON array"} />
              <p className="mt-2 text-[11px] leading-relaxed text-[#6D7175]">Use the fields required by the selected backend handler. The app does not invent Shopify IDs or values.</p>
            </div>
          )}

          {/* Validation error */}
          {validationError && (
            <div
              role="alert"
              className="flex gap-2 rounded-lg border border-[#FFC9C5] bg-[#FFF0EF] p-3 text-xs leading-relaxed text-[#D72C0D]"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          {/* Request result */}
          {requestSucceeded && (
            <div
              role="status"
              className="flex gap-2 rounded-lg border border-[#A7F3D0] bg-[#ECFDF5] p-3 text-xs leading-relaxed text-[#065F46]"
            >
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">Backend reported success.</p>
                <p className="mt-1">
                  {responseMessage ||
                    "The store-wide fix request completed successfully."}
                </p>
              </div>
            </div>
          )}

          {requestFailed && (
            <div
              role="alert"
              className="flex gap-2 rounded-lg border border-[#FFC9C5] bg-[#FFF0EF] p-3 text-xs leading-relaxed text-[#D72C0D]"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">Could not apply the fix.</p>
                <p className="mt-1">
                  {responseMessage ||
                    "The request failed. Check the backend response and issue configuration."}
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-col-reverse gap-2 border-t border-[#E1E3E5] pt-4 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-md border border-[#E1E3E5] px-4 py-2 text-xs font-semibold text-[#202223] hover:bg-[#F8F9FA] disabled:opacity-50"
            >
              {requestSucceeded ? "Close" : "Cancel"}
            </button>

            {!requestSucceeded && (
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111111] px-4 py-2 text-xs font-semibold text-white hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                    Applying fix...
                  </>
                ) : (
                  <>
                    <Wrench className="h-4 w-4" />
                    Review and apply fix
                  </>
                )}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

StoreFixModal.propTypes = {
  issue: PropTypes.shape({
    priority: PropTypes.string,
    enrichment: PropTypes.string,
    why_it_matters_for_agents: PropTypes.string,
    example: PropTypes.string,
    affectedProducts: PropTypes.arrayOf(
      PropTypes.shape({
        product_id: PropTypes.oneOfType([
          PropTypes.string,
          PropTypes.number,
        ]),
        title: PropTypes.string,
      })
    ),
    raw: PropTypes.object,
  }).isRequired,
  shopDomain: PropTypes.string.isRequired,
  onClose: PropTypes.func.isRequired,
};

/* -------------------------------------------------------------------------- */
/* Issues page                                                                */
/* -------------------------------------------------------------------------- */

export default function Issues() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All");
  const [expandedKey, setExpandedKey] = useState(null);
  const [selectedIssue, setSelectedIssue] = useState(null);

  useEffect(() => {
    if (!shopDomain) {
      setLoading(false);
      setReport(null);
      return;
    }

    let cancelled = false;

    async function loadAudit() {
      setLoading(true);
      setLoadError("");

      try {
        const response = await fetch(
          `https://geo.properoapps.in/api/audits/latest?shop_domain=${encodeURIComponent(
            shopDomain
          )}`
        );

        if (response.status === 404) {
          if (!cancelled) {
            setReport(null);
            setLoading(false);
          }
          return;
        }

        if (!response.ok) {
          throw new Error(
            `Failed to load the latest audit (${response.status}).`
          );
        }

        const data = await response.json();

        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (error) {
        console.error("Failed to load latest audit:", error);

        if (!cancelled) {
          setReport(null);
          setLoadError(
            error.message || "Unable to load the latest audit."
          );
          setLoading(false);
        }
      }
    }

    loadAudit();

    return () => {
      cancelled = true;
    };
  }, [shopDomain]);

  /*
   * Keep the complete recommendation in `raw`.
   * The Fix modal reads only real fields from this object.
   */
  const allIssues = useMemo(() => {
    const products = Array.isArray(report?.products)
      ? report.products
      : [];

    const storeRecs = Array.isArray(report?.store_level_recommendations)
      ? report.store_level_recommendations
      : [];

    // The audit endpoint returns the registered issues for this audit.
    const auditIssues = Array.isArray(report?.issues)
      ? report.issues
      : [];

    return storeRecs.map((recommendation, index) => {
      const resolvedMetadata = resolveStoreFixMetadata(
        recommendation,
        auditIssues
      );

      // Prefer metadata attached to this recommendation by the backend.
      const raw = {
        ...recommendation,
        check_id:
          recommendation.check_id ||
          recommendation.fix_payload?.check_id ||
          resolvedMetadata.check_id,
        issue_type:
          recommendation.issue_type ||
          recommendation.fix_payload?.issue_type ||
          resolvedMetadata.issue_type,
        issue_id:
          recommendation.issue_id ||
          recommendation.fix_payload?.issue_id ||
          resolvedMetadata.issue_id,
        fix_action:
          recommendation.fix_action ||
          recommendation.fix_payload?.fix_action ||
          resolvedMetadata.fix_action,
        store_issues: resolvedMetadata.store_issues,
        metadata_supplied: resolvedMetadata.supplied,
      };

      return {
        key: `store-${index}`,
        priority: getPriority(recommendation.priority),
        enrichment: recommendation.enrichment || "Missing enrichment",
        why_it_matters_for_agents:
          recommendation.why_it_matters_for_agents || "",
        example: recommendation.example || "",
        affectedProducts: getAffectedProducts(recommendation, products),
        raw,
      };
    });
  }, [
    report?.store_level_recommendations,
    report?.products,
    report?.issues,
  ]);

  const highCount = allIssues.filter(
    (issue) => issue.priority === "high"
  ).length;

  const mediumCount = allIssues.filter(
    (issue) => issue.priority === "medium"
  ).length;

  const lowCount = allIssues.filter(
    (issue) => issue.priority === "low"
  ).length;

  const filteredIssues = useMemo(() => {
    const query = search.trim().toLowerCase();

    return allIssues.filter((issue) => {
      const matchesSeverity =
        severity === "All" || issue.priority === severity.toLowerCase();

      const matchesSearch =
        !query ||
        issue.enrichment.toLowerCase().includes(query) ||
        issue.affectedProducts.some((product) =>
          String(product.title || "")
            .toLowerCase()
            .includes(query)
        );

      return matchesSeverity && matchesSearch;
    });
  }, [allIssues, search, severity]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#202223]">
            Issues
          </h1>

          <p className="mt-0.5 text-sm text-[#6D7175]">
            Store-level issues and recommendations identified in your latest
            audit.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#E1E3E5] bg-white px-3 py-1.5 text-xs shadow-sm">
          <span className="font-semibold text-[#202223]">
            Audit Status:
          </span>

          <span className="font-bold text-[#D72C0D]">
            {highCount} High
          </span>

          <span className="text-[#E1E3E5]">•</span>

          <span className="font-bold text-[#8A6116]">
            {mediumCount} Medium
          </span>

          <span className="text-[#E1E3E5]">•</span>

          <span className="font-bold text-[#6D7175]">
            {lowCount} Low
          </span>
        </div>
      </div>

      {/* Search and severity filters */}
      <div className="space-y-3 rounded-xl border border-[#E1E3E5] bg-white p-4 shadow-sm">
        <div className="flex flex-col items-stretch justify-between gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#6D7175]" />

            <input
              type="text"
              placeholder="Search issues or products..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-md border border-[#E1E3E5] py-2 pl-9 pr-4 text-xs text-[#202223] outline-none placeholder:text-[#6D7175] focus:border-[#D97706] focus:ring-1 focus:ring-[#D97706]"
            />
          </div>

          <div className="flex shrink-0 items-center gap-1 rounded-md bg-[#F1F2F3] p-1">
            {["All", "High", "Medium", "Low"].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setSeverity(value)}
                className={`cursor-pointer rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
                  severity === value
                    ? "bg-white text-[#202223] shadow-sm"
                    : "text-[#6D7175] hover:text-[#202223]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Issues table */}
      <div className="overflow-hidden rounded-xl border border-[#E1E3E5] bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-[#E1E3E5] p-4 text-xs text-[#6D7175]">
          <div>
            Showing{" "}
            <span className="font-bold text-[#202223]">
              {filteredIssues.length}
            </span>{" "}
            issues
          </div>

          <div className="text-[11px] text-[#6D7175]">
            Expand an issue to view details
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center">
            <LoaderCircle className="mx-auto mb-3 h-7 w-7 animate-spin text-[#D97706]" />
            <p className="text-sm font-semibold text-[#202223]">
              Loading audit issues...
            </p>
          </div>
        ) : loadError ? (
          <div className="py-16 text-center">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#D72C0D]" />
            <p className="text-sm font-semibold text-[#202223]">
              Unable to load issues
            </p>
            <p className="mt-1 text-xs text-[#6D7175]">
              {loadError}
            </p>
          </div>
        ) : !report ? (
          <div className="py-16 text-center">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />
            <p className="text-sm font-semibold text-[#202223]">
              No audit report available
            </p>
            <p className="mt-1 text-xs text-[#6D7175]">
              Run an audit from the Dashboard first.
            </p>
          </div>
        ) : filteredIssues.length === 0 ? (
          <div className="py-12 text-center text-[#6D7175]">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />
            <p className="text-sm font-semibold text-[#202223]">
              No issues matching your filters
            </p>
            <p className="mt-1 text-xs">
              Try adjusting the search or severity filter.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead className="bg-[#F8F9FA] text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                <tr>
                  <th className="w-28 border-b border-[#E1E3E5] px-5 py-3">
                    Severity
                  </th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3">
                    Issue
                  </th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3">
                    Affected Products
                  </th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3 text-right">
                    View Issue
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-[#E1E3E5] text-xs">
                {filteredIssues.map((issue) => {
                  const isExpanded = expandedKey === issue.key;
                  const recommendation = issue.raw || {};

                  const affectedLabel =
                    issue.affectedProducts.length > 0
                      ? `${issue.affectedProducts.length} product${
                          issue.affectedProducts.length === 1 ? "" : "s"
                        }`
                      : "Store-wide";

                  return (
                    <Fragment key={issue.key}>
                      <tr
                        className="group cursor-pointer transition-colors hover:bg-[#F9FAFB]"
                        onClick={() =>
                          setExpandedKey(isExpanded ? null : issue.key)
                        }
                      >
                        <td className="whitespace-nowrap px-5 py-4 align-top">
                          <SeverityBadge priority={issue.priority} />
                        </td>

                        <td className="px-5 py-4 align-top">
                          <div className="font-semibold text-[#202223] transition-colors group-hover:text-[#D97706]">
                            {issue.enrichment}
                          </div>
                        </td>

                        <td className="whitespace-nowrap px-5 py-4 align-top">
                          <span className="inline-flex items-center gap-1.5 font-medium text-[#202223]">
                            {affectedLabel}
                          </span>
                        </td>

                        <td className="whitespace-nowrap px-5 py-4 text-right align-top">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setExpandedKey(isExpanded ? null : issue.key);
                            }}
                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold text-[#8A6116] transition-colors hover:underline"
                          >
                            <span>
                              {isExpanded ? "Hide Issue" : "View Issue"}
                            </span>

                            {isExpanded ? (
                              <ChevronUp className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr>
                          <td
                            colSpan={4}
                            className="border-t border-[#F1F2F3] bg-[#FAFAFA] px-5 py-4"
                          >
                            {(
                              issue.why_it_matters_for_agents ||
                              recommendation.description ||
                              recommendation.recommendation ||
                              recommendation.enrichment
                            ) && (
                              <div className="mt-3">
                                <p className="mb-1 text-xs font-semibold text-[#202223]">
                                  Recommendation
                                </p>
                                <p className="text-xs leading-relaxed text-[#6D7175]">
                                  {issue.why_it_matters_for_agents ||
                                    recommendation.description ||
                                    recommendation.recommendation ||
                                    recommendation.enrichment}
                                </p>
                              </div>
                            )}

                            {issue.example && (
                              <div className="mt-3 whitespace-pre-line rounded-lg border-l-2 border-[#D97706] bg-white px-3 py-2 font-mono text-[11px] text-[#6D7175]">
                                {issue.example}
                              </div>
                            )}

                            {issue.affectedProducts.length > 0 && (
                              <div className="mt-3">
                                <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                  Affected products
                                </div>

                                <div className="flex flex-wrap gap-2">
                                  {issue.affectedProducts.map((product) => (
                                    <button
                                      key={product.product_id}
                                      type="button"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        navigate(
                                          `/app/products/detail?id=${encodeURIComponent(
                                            product.product_id
                                          )}`
                                        );
                                      }}
                                      className="rounded-full border border-[#E1E3E5] bg-white px-3 py-1 text-xs font-semibold text-[#8A6116] hover:underline"
                                    >
                                      {product.title || product.product_id}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#E1E3E5] pt-3">
                              <p className="text-[11px] leading-relaxed text-[#6D7175]">
                                Review the actual change payload before
                                applying a store-wide fix.
                              </p>

                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedIssue(issue);
                                }}
                                className="inline-flex items-center gap-2 rounded-md bg-[#111111] px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#333333]"
                              >
                                <Wrench className="h-3.5 w-3.5" />
                                Fix Issue
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Store-wide fix dialog */}
      {selectedIssue && (
        <StoreFixModal
          key={selectedIssue.key}
          issue={selectedIssue}
          shopDomain={shopDomain}
          onClose={() => setSelectedIssue(null)}
        />
      )}
    </div>
  );
}
