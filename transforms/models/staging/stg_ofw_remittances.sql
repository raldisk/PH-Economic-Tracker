{{
    config(
        materialized='view',
        description='Cleaned OFW remittance records from raw.ofw_remittances.'
    )
}}

with source as (

    select * from {{ source('raw', 'ofw_remittances') }}

),

cleaned as (

    select
        id,
        source,
        period_date,
        frequency,
        remittance_usd,
        remittance_pct_gdp,
        coalesce(nullif(trim(country_destination), ''), 'ALL') as country_destination,
        ofw_count,
        notes,
        loaded_at,

        -- Derived
        extract('year'   from period_date)::integer         as period_year,
        extract('month'  from period_date)::integer         as period_month,
        extract('quarter' from period_date)::integer        as period_quarter,

        -- USD billions for readability
        round(remittance_usd / 1000000000.0, 3)             as remittance_usd_bn,

        -- Label for chart display
        to_char(period_date, 'YYYY-MM')                     as period_label

    from source
    where remittance_usd is not null
       or remittance_pct_gdp is not null

)

select * from cleaned
