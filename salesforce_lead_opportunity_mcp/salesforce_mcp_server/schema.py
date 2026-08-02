"""Allowlisted Salesforce fields exposed by this MCP server.

Update custom-field API names to match your Salesforce org.
"""

from typing import Final

LEAD_FIELDS: Final[dict[str, str]] = {
    "id": "Id",
    "first_name": "FirstName",
    "last_name": "LastName",
    "name": "Name",
    "company": "Company",
    "title": "Title",
    "email": "Email",
    "phone": "Phone",
    "mobile_phone": "MobilePhone",
    "website": "Website",
    "industry": "Industry",
    "annual_revenue": "AnnualRevenue",
    "number_of_employees": "NumberOfEmployees",
    "lead_source": "LeadSource",
    "status": "Status",
    "rating": "Rating",
    "street": "Street",
    "city": "City",
    "state": "State",
    "postal_code": "PostalCode",
    "country": "Country",
    "created_date": "CreatedDate",
    "last_modified_date": "LastModifiedDate",
    "is_converted": "IsConverted",
    "converted_account_id": "ConvertedAccountId",
    "converted_contact_id": "ConvertedContactId",
    "converted_opportunity_id": "ConvertedOpportunityId",
    "utm_source": "utm_source__c",
    "utm_campaign": "utm_campaign__c",
    "gclid": "GCLID__c",
    # Replace this with your custom field only if it exists:
    # "external_opportunity_id": "Converted_Opportunity_ID__c",
}

OPPORTUNITY_FIELDS: Final[dict[str, str]] = {
    "id": "Id",
    "name": "Name",
    "account_id": "AccountId",
    "account_name": "Account.Name",
    "stage_name": "StageName",
    "amount": "Amount",
    "probability": "Probability",
    "close_date": "CloseDate",
    "type": "Type",
    "lead_source": "LeadSource",
    "forecast_category": "ForecastCategoryName",
    "next_step": "NextStep",
    "description": "Description",
    "owner_id": "OwnerId",
    "owner_name": "Owner.Name",
    "created_date": "CreatedDate",
    "last_modified_date": "LastModifiedDate",
    "is_closed": "IsClosed",
    "is_won": "IsWon",
    # Examples from your existing org; uncomment only when present:
    # "external_opportunity_id": "Opportunity_ID__c",
    # "arr": "ARR__c",
    # "sales_rep_name": "Sales_Rep_Name__c",
    # "risks": "Risks__c",
    # "manager_notes": "Manager_Notes__c",
}

OBJECT_FIELDS: Final[dict[str, dict[str, str]]] = {
    "Lead": LEAD_FIELDS,
    "Opportunity": OPPORTUNITY_FIELDS,
}
