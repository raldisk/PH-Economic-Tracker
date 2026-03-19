{{
    config(
        materialized='table',
        description='Wide annual dashboard table joining GDP, CPI, and OFW remittances by year. Primary source for the Streamlit dashboard summary cards.'
    )
}}

with gdp as (
    select
        period_year,
        gdp_usd_bn,
        gdp_growth_pct,
        gdp_per_capita_usd
    from {{ ref('gdp_trend') }}
),

cpi as (
    -- Annual average from monthly series
    select
        period_year,
        round(avg(cpi_index), 2)        as avg_cpi_index,
        round(avg(inflation_pct), 2)    as avg_inflation_pct
    from {{ ref('cpi_trend') }}
    where cpi_index is not null
    group by period_year
),

remittance as (
    select
        period_year,
        remittance_usd_bn,
        remittance_pct_gdp,
        remittance_yoy_pct
    from {{ ref('remittance_trend') }}
)

select
    coalesce(g.period_year, c.period_year, r.period_year)       as period_year,

    -- GDP
    g.gdp_usd_bn,
    g.gdp_growth_pct,
    g.gdp_per_capita_usd,

    -- CPI / Inflation
    c.avg_cpi_index,
    c.avg_inflation_pct,

    -- OFW Remittances
    r.remittance_usd_bn,
    r.remittance_pct_gdp,
    r.remittance_yoy_pct,

    -- Remittances as share of GDP (cross-validated)
    round(
        r.remittance_usd_bn / nullif(g.gdp_usd_bn, 0) * 100
    , 2)                                                         as remit_to_gdp_pct_computed

from gdp g
full outer join cpi       c on g.period_year = c.period_year
full outer join remittance r on g.period_year = r.period_year

where coalesce(g.period_year, c.period_year, r.period_year) is not null
order by 1
