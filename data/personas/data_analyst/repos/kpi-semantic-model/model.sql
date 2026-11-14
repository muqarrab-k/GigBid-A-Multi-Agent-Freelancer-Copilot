CREATE VIEW dbo.dim_date AS
SELECT
    d.[DateKey],
    d.[Date],
    d.[Year],
    d.[Quarter],
    d.[MonthNumber],
    d.[MonthName],
    d.[DayOfMonth]
FROM dbo.DateDimension d;
GO

CREATE VIEW dbo.dim_product AS
SELECT
    p.ProductKey,
    p.ProductCode,
    p.ProductName,
    p.ProductCategory,
    p.ProductSubcategory
FROM dbo.ProductDimension p;
GO

CREATE VIEW dbo.dim_customer AS
SELECT
    c.CustomerKey,
    c.CustomerCode,
    c.CustomerName,
    c.Region,
    c.Country
FROM dbo.CustomerDimension c;
GO

CREATE VIEW dbo.dim_salesperson AS
SELECT
    s.SalespersonKey,
    s.SalespersonName,
    s.TeamName,
    s.ManagerName
FROM dbo.SalespersonDimension s;
GO

CREATE VIEW dbo.fact_sales AS
SELECT
    f.SalesKey,
    f.DateKey,
    f.ProductKey,
    f.CustomerKey,
    f.SalespersonKey,
    f.OrderNumber,
    f.Quantity,
    f.UnitPrice,
    f.DiscountAmount,
    f.NetSalesAmount
FROM dbo.SalesFact f;
GO
