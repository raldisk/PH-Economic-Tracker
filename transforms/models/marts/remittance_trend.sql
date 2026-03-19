{{
    config(
        materialized='table',
        description='OFW remittance trend — annual totals with YoY growth rate and 3-year rolling average.'
    )
}}

with base as (

    select * from {{ ref('stg_ofw_remittances') }}
    where country_destination = 'ALL'

),

annual as (

    select
        period_year,
        period_date,
        source,
        frequency,
        remittance_usd,
        remittance_usd_bn,
        remittance_pct_gdp,
        ofw_count,
        period_label

    from base
    where frequency = 'ANNUAL'

),

-- Compute prev_remittance_usd once here; reference it downstream.
-- Previously lag() was evaluated 3 separate times — any change to
-- partition/order key required 3 edits with silent inconsistency risk.
with_lag as (

    select
        period_year,
        period_date,
        source,
        remittance_usd,
        remittance_usd_bn,
        remittance_pct_gdp,
        ofw_count,
        period_label,

        lag(remittance_usd) over (
            order by period_year
        )                                                       as prev_remittance_usd,

        -- 3-year rolling average (smooths election-year spikes)
        round(
            avg(remittance_usd) over (
                order by period_year
                rows between 2 preceding and current row
            ) / 1000000000.0
        , 3)                                                    as remittance_3yr_avg_bn

    from annual

),

with_growth as (

    select
        period_year,
        period_date,
        source,
        remittance_usd,
        remittance_usd_bn,
        remittance_pct_gdp,
        ofw_count,
        period_label,
        prev_remittance_usd,
        remittance_3yr_avg_bn,

        -- Both derived columns reference prev_remittance_usd once — single source of truth
        remittance_usd - prev_remittance_usd                   as remittance_yoy_change_usd,

        round(
            (remittance_usd - prev_remittance_usd)
            / nullif(prev_remittance_usd, 0) * 100
        , 2)                                                    as remittance_yoy_pct

    from with_lag

)

select * from with_growth
order by period_year
