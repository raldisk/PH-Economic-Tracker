{{
    config(
        materialized='table',
        description='GDP trend — annual series with YoY growth rate and per-capita.'
    )
}}

with base as (

    select * from {{ ref('stg_economic_indicators') }}
    where indicator_type = 'gdp'
      and source = 'WORLD_BANK'

),

gdp_current as (
    select period_year, period_date, value as gdp_usd
    from base where series_code = 'NY.GDP.MKTP.CD'
),

gdp_growth as (
    select period_year, value as gdp_growth_pct
    from base where series_code = 'NY.GDP.MKTP.KD.ZG'
),

gdp_per_capita as (
    select period_year, value as gdp_per_capita_usd
    from base where series_code = 'NY.GDP.PCAP.CD'
),

joined as (

    select
        c.period_year,
        c.period_date,
        c.gdp_usd,
        round(c.gdp_usd / 1000000000.0, 3)    as gdp_usd_bn,
        g.gdp_growth_pct,
        p.gdp_per_capita_usd,

        -- YoY change in absolute GDP (computed, not from WB series)
        lag(c.gdp_usd) over (order by c.period_year) as prev_gdp_usd,

        c.gdp_usd - lag(c.gdp_usd) over (
            order by c.period_year
        )                                                   as gdp_yoy_change_usd

    from gdp_current c
    left join gdp_growth    g using (period_year)
    left join gdp_per_capita p using (period_year)

)

select
    period_year,
    period_date,
    gdp_usd,
    gdp_usd_bn,
    gdp_growth_pct,
    gdp_per_capita_usd,
    prev_gdp_usd,
    gdp_yoy_change_usd,
    round(gdp_yoy_change_usd / nullif(prev_gdp_usd, 0) * 100, 2) as gdp_yoy_pct_computed

from joined
order by period_year
