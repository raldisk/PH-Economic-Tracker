{{
    config(
        materialized='view',
        description='Cleaned economic indicators from raw.economic_indicators.'
    )
}}

with source as (

    select * from {{ source('raw', 'economic_indicators') }}

),

cleaned as (

    select
        id,
        source,
        upper(trim(series_code))                            as series_code,
        trim(series_name)                                   as series_name,
        period_date,
        frequency,
        value,
        nullif(trim(unit), '')                              as unit,
        coalesce(nullif(trim(country_code), ''), 'PH')     as country_code,
        notes,
        loaded_at,

        -- Derived
        extract('year'  from period_date)::integer          as period_year,
        extract('month' from period_date)::integer          as period_month,
        extract('quarter' from period_date)::integer        as period_quarter,

        -- Classify indicator type for downstream mart routing
        case
            when series_code ilike '%GDP%'
              or series_code = 'NY.GDP.MKTP.CD'
              or series_code = 'NY.GDP.MKTP.KD.ZG'
              or series_code = 'NY.GDP.PCAP.CD'            then 'gdp'
            when series_code ilike '%CPI%'
              or series_code = 'FP.CPI.TOTL.ZG'            then 'cpi'
            when series_code ilike '%UNEM%'
              or series_code = 'SL.UEM.TOTL.ZS'            then 'employment'
            else 'other'
        end                                                  as indicator_type

    from source
    where value is not null

)

select * from cleaned
